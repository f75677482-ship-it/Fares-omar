/* worker.js — Isolated WhatsApp worker process. ONE process per linked number.
 *
 * Architecture:
 *   index.py (Python orchestrator)
 *     ├── spawns Node companion (server.js) ONCE  → handles pair code + writes creds
 *     ├── receives /pair/webhook from companion
 *     └── spawns THIS script PER linked number  → maintains a single WhatsApp session
 *
 * Environment (set by index.py):
 *   WORKER_PHONE        normalised phone (digits only)
 *   WORKER_SESSION_ID   unique session id (default phone)
 *   WORKER_SESSION_DIR  absolute directory containing creds.json
 *   WORKER_USER_ID      telegram user id that owns this number
 *   WORKER_ALIVE_MESSAGE  message sent to the number itself the moment it connects
 *   WORKER_LINKED_AT    ISO timestamp
 *   WORKER_SITE_PASSWORD  DRF site password
 *   WORKER_BOT_LINK    DRF site URL
 *   WORKER_MONGO_URI   optional; mirror creds into MongoDB
 *   WORKER_MONGO_DB    db name
 *   WORKER_MONGO_COLL  sessions collection
 *   WORKER_COMPANION_URL  used only for post-link webhook
 *   WORKER_CHILD=1     marker
 *
 * Output protocol — JSON lines on stdout:
 *   {"type":"log","msg":"..."}
 *   {"type":"booted","phone":"...","session_id":"..."}
 *   {"type":"credentials_saved"}
 *   {"type":"connected","phone":"...","session_id":"..."}
 *   {"type":"alive_sent"}
 *   {"type":"message","from":"...","text":"...","id":"..."}
 *   {"type":"reconnecting","attempt":N}
 *   {"type":"fatal","reason":"...","message":"..."}
 *
 * The orchestrator separates stdout JSON from readable [worker] logs so it
 * never blocks or pauses when this process is chatty.
 */
/* eslint-disable */
'use strict';

const fs   = require('fs');
const fsp  = fs.promises;
const path = require('path');
const { EventEmitter } = require('events');
process.title = `wa-worker-${process.env.WORKER_SESSION_ID || 'anon'}`;

EventEmitter.defaultMaxListeners = 0;

const phone         = String(process.env.WORKER_PHONE || '').replace(/\D/g, '');
const sessionId     = String(process.env.WORKER_SESSION_ID || phone);
const sessionDir    = String(process.env.WORKER_SESSION_DIR || '');
const ownerId       = parseInt(process.env.WORKER_USER_ID || '0', 10) || 0;
const aliveMessage  = String(process.env.WORKER_ALIVE_MESSAGE || '');
const linkedAt      = String(process.env.WORKER_LINKED_AT || new Date().toISOString());
const sitePassword  = String(process.env.WORKER_SITE_PASSWORD || '');
const botLink       = String(process.env.WORKER_BOT_LINK || '');
const mongoUri      = String(process.env.WORKER_MONGO_URI || '').trim();
const mongoDb       = String(process.env.WORKER_MONGO_DB || 'whatsapp_pairing_api');
const mongoColl     = String(process.env.WORKER_MONGO_COLL || 'whatsapp_sessions');
const companionUrl  = String(process.env.WORKER_COMPANION_URL || '').trim();

if (!phone || !sessionDir) {
    process.stdout.write(JSON.stringify({ type: 'fatal', reason: 'missing_env' }) + '\n');
    process.exit(2);
}

// stdout is reserved for JSON events only — keep it pristine
const emit = (obj) => {
    try {
        const line = JSON.stringify(obj);
        process.stdout.write(line + '\n');
    } catch (_) { /* pipe may be closed by orchestrator reader */ }
};
const log = (msg) => emit({ type: 'log', msg });

let makeWASocket, fetchLatestBaileysVersion, Browsers, DisconnectReason, delay, useMultiFileAuthState;
try {
    const bw = require('@whiskeysockets/baileys');
    makeWASocket           = bw.default || bw.makeWASocket;
    fetchLatestBaileysVersion = bw.fetchLatestBaileysVersion;
    Browsers               = bw.Browsers;
    DisconnectReason       = bw.DisconnectReason;
    delay                  = bw.delay;
    useMultiFileAuthState  = bw.useMultiFileAuthState;
} catch (e) {
    emit({ type: 'fatal', reason: 'baileys_missing', message: String(e.message || e) });
    process.exit(3);
}

// pino is silenced so its noise never reaches stderr in mixed mode.
const { pino } = require('pino');
const logger = pino({ level: 'silent' });

// ----------------------------------------------------------------------
// Mongo mirror (optional)
let mongoClient = null;
async function mirrorCredsToMongo(credsJson) {
    if (!mongoUri) return;
    try {
        if (!mongoClient) {
            const { MongoClient } = require('mongodb');
            mongoClient = new MongoClient(mongoUri, { serverSelectionTimeoutMS: 8000 });
            await mongoClient.connect();
        }
        const db = mongoClient.db(mongoDb);
        let creds = null;
        try { creds = JSON.parse(credsJson); } catch (_) { creds = null; }
        await db.collection(mongoColl).updateOne(
            { jid: phone },
            { $set: { jid: phone, sessionId, creds, updatedAt: new Date(), ownerId, linkedAt, sitePassword, botLink } },
            { upsert: true }
        );
    } catch (e) {
        log(`mongo mirror failed: ${e.message}`);
    }
}

async function closeMongo() {
    if (mongoClient) {
        try { await mongoClient.close(); } catch (_) {}
        mongoClient = null;
    }
}

// ----------------------------------------------------------------------
// Helpers
async function sendAliveToSelf(sock) {
    if (!aliveMessage) return;
    try {
        await sock.sendMessage(`${phone}@s.whatsapp.net`, { text: aliveMessage });
        emit({ type: 'alive_sent' });
    } catch (e) {
        log(`alive self-send failed: ${e.message}`);
    }
}

async function postLinkWebhook() {
    if (!companionUrl) return;
    try {
        const url = companionUrl.replace(/\/$/, '') + '/pair/webhook';
        const ctrl = new AbortController();
        const t = setTimeout(() => ctrl.abort(), 4000);
        await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                phone, session_id: sessionId, user_id: ownerId, linked_at: linkedAt,
                site_password: sitePassword, bot_link: botLink,
            }),
            signal: ctrl.signal,
        }).catch(() => {});
        clearTimeout(t);
    } catch (_) {}
}

// ----------------------------------------------------------------------
// Main
async function start() {
    if (!fs.existsSync(sessionDir)) await fsp.mkdir(sessionDir, { recursive: true });
    const credsPath = path.join(sessionDir, 'creds.json');
    if (!fs.existsSync(credsPath)) {
        // No creds yet (first pairing in progress) — wait briefly and retry a few times,
        // the companion writes them within seconds after `/pair` is called.
        for (let i = 0; i < 30; i++) {
            await delay(500);
            if (fs.existsSync(credsPath)) break;
        }
    }
    if (!fs.existsSync(credsPath)) {
        emit({ type: 'fatal', reason: 'no_creds', message: 'creds.json missing in sessionDir after wait' });
        // Stay alive a bit so the orchestrator can decide to either respawn or give up
        setTimeout(() => process.exit(7), 5000);
        return;
    }

    const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
    const { version } = await fetchLatestBaileysVersion().catch(() => ({ version: [2, 3000, 1015901307] }));

    const sock = makeWASocket({
        version,
        logger,
        browser: Browsers.ubuntu('Chrome'),
        auth: state,
        printQRInTerminal: false,
        generateHighQualityLinkPreview: false,
        markOnlineOnConnect: true,
        syncFullHistory: false,
    });

    sock.ev.on('creds.update', async () => {
        try {
            await saveCreds();
            emit({ type: 'credentials_saved' });
            const credsJson = await fsp.readFile(credsPath, 'utf8').catch(() => '{}');
            await mirrorCredsToMongo(credsJson);
        } catch (e) {
            log(`creds.save failed: ${e.message}`);
        }
    });

    let inFlightSends = new Map(); // id -> promise (kept to surface later)
    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect } = update;
        if (connection === 'open') {
            emit({ type: 'connected', phone, session_id: sessionId });
            await postLinkWebhook();
            await sendAliveToSelf(sock);
        } else if (connection === 'close') {
            const status = lastDisconnect?.error?.output?.statusCode;
            const loggedOut = status === DisconnectReason.loggedOut;
            emit({ type: 'fatal', reason: 'closed', status, loggedOut });
            // Single-process policy: tell orchestrator via exit code; orchestrator respawns.
            // We do an internal backoff before exiting so we don't spin in tight loop if the
            // orchestrator briefly stops reading this pipe.
            const backoff = 2000 + Math.floor(Math.random() * 2000);
            log(`exiting in ${backoff}ms (loggedOut=${loggedOut})`);
            setTimeout(() => process.exit(loggedOut ? 5 : 0), backoff);
        } else if (connection === 'connecting') {
            log(`connecting (attempt for ${phone})`);
        }
    });

    sock.ev.on('messages.upsert', async (m) => {
        try {
            const msgs = Array.isArray(m.messages) ? m.messages : [];
            for (const msg of msgs) {
                if (!msg || !msg.message || msg.key?.fromMe) continue;
                const text = msg.message.conversation
                          || (msg.message.extendedTextMessage && msg.message.extendedTextMessage.text)
                          || '';
                if (!text) continue;
                emit({ type: 'message', from: msg.key.remoteJid, text: String(text).slice(0, 256), id: msg.key.id });
            }
        } catch (_) {}
    });

    // Internal self-resilience: if orchestrator takes longer than 30s, attempt
    // an internal reconnect once before exiting (avoids depending on respawn).
    let selfAttempts = 0;
    let selfRespawning = false;
    sock.ev.on('connection.update', async (update) => {
        if (selfRespawning) return;
        if (update.connection !== 'close') return;
        const status = update.lastDisconnect?.error?.output?.statusCode;
        if (status === DisconnectReason.loggedOut) return;
        selfAttempts++;
        if (selfAttempts > 2) return;  // give up, let orchestrator respawn
        selfRespawning = true;
        emit({ type: 'reconnecting', attempt: selfAttempts });
        await delay(Math.min(15000, 4000 * selfAttempts));
        try {
            await sock.end();
        } catch (_) {}
        try {
            selfRespawning = false;
            await start();
        } catch (e) {
            emit({ type: 'fatal', reason: 'self_respawn_failed', message: String(e.message || e) });
            process.exit(6);
        }
    });

    // Track & resolve any in-flight send requests when the socket closes
    sock.ev.on('connection.update', (update) => {
        for (const [id, p] of inFlightSends) {
            p.reject(new Error('socket closed mid-send'));
            inFlightSends.delete(id);
        }
    });

    process.on('SIGTERM', async () => { try { await sock.end(); } catch (_) {} await closeMongo(); process.exit(0); });
    process.on('SIGINT',  async () => { try { await sock.end(); } catch (_) {} await closeMongo(); process.exit(0); });
    process.on('SIGHUP',  async () => { try { await sock.end(); } catch (_) {} await closeMongo(); process.exit(0); });
    process.on('uncaughtException', (err) => { log(`uncaught: ${err.message}`); });

    emit({ type: 'booted', phone, session_id: sessionId });
    return sock;
}

(async () => {
    try {
        await start();
    } catch (e) {
        emit({ type: 'fatal', reason: 'start_failed', message: String(e.message || e) });
        await closeMongo();
        process.exit(4);
    }
})();
