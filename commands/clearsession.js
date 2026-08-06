const fs = require('fs');
const path = require('path');
const { listMongoSessionJsonFiles, clearMongoSessionAuthFiles, deleteMongoSessionSnapshot } = require('../mongo-auth');
const isOwnerOrSudo = require('../lib/isOwner');
const { DATA_DIR, SESSION_ROOT } = require('../lib/storagePaths');
const { deleteRemotePhoneSettings } = require('../lib/remotePhoneSettingsStore');

const channelInfo = {
    contextInfo: {
        forwardingScore: 999,
        isForwarded: true,
        forwardedNewsletterMessageInfo: {
            newsletterJid: '120363161513685998@newsletter',
            newsletterName: 'KnightBot MD',
            serverMessageId: -1
        }
    }
};

const USERS_FILE = path.join(DATA_DIR, 'users.json');
const PHONE_SETTINGS_FILE = path.join(DATA_DIR, 'phone-settings.json');
const SESSION_STORE_FILE = path.join(DATA_DIR, 'session-store.json');

function normalizePhone(value = '') {
    return String(value || '').replace(/\D/g, '').trim();
}

function readJsonSafe(filePath, fallback) {
    try {
        return JSON.parse(fs.readFileSync(filePath, 'utf8'));
    } catch (_) {
        return fallback;
    }
}

function writeJsonSafe(filePath, data) {
    try {
        fs.mkdirSync(path.dirname(filePath), { recursive: true });
        fs.writeFileSync(filePath, JSON.stringify(data, null, 2), 'utf8');
        return true;
    } catch (_) {
        return false;
    }
}

function removeSessionDirectory(phone) {
    const normalized = normalizePhone(phone);
    if (!normalized) return false;
    try {
        fs.rmSync(path.join(SESSION_ROOT, normalized), { recursive: true, force: true });
        return true;
    } catch (_) {
        return false;
    }
}

function removePhoneFromUsers(phone) {
    const normalized = normalizePhone(phone);
    if (!normalized) return false;

    const db = readJsonSafe(USERS_FILE, { users: {}, phoneOwners: {} });
    db.users = db.users || {};
    db.phoneOwners = db.phoneOwners || {};

    const ownerId = db.phoneOwners[normalized];
    if (ownerId && db.users[ownerId]) {
        db.users[ownerId].linkedNumbers = (db.users[ownerId].linkedNumbers || []).filter((item) => normalizePhone(item) !== normalized);
        if (db.users[ownerId].emojis && typeof db.users[ownerId].emojis === 'object') {
            delete db.users[ownerId].emojis[normalized];
        }
        db.users[ownerId].updatedAt = new Date().toISOString();
    }

    delete db.phoneOwners[normalized];
    writeJsonSafe(USERS_FILE, db);
    return true;
}

function removePhoneSettings(phone) {
    const normalized = normalizePhone(phone);
    if (!normalized) return false;

    const db = readJsonSafe(PHONE_SETTINGS_FILE, { profiles: {} });
    db.profiles = db.profiles || {};
    if (db.profiles[normalized]) {
        delete db.profiles[normalized];
        writeJsonSafe(PHONE_SETTINGS_FILE, db);
    }

    const sessionProfileFiles = [
        path.join(SESSION_ROOT, normalized, 'phone-settings-profile.json'),
        path.join(SESSION_ROOT, normalized, 'phone-settings-credentials.json'),
        path.join(SESSION_ROOT, normalized, 'phone-settings-meta.json')
    ];

    for (const filePath of sessionProfileFiles) {
        try {
            fs.rmSync(filePath, { force: true });
        } catch (_) {}
    }

    return true;
}

function removeSessionStoreRecord(phone) {
    const normalized = normalizePhone(phone);
    if (!normalized) return false;

    const db = readJsonSafe(SESSION_STORE_FILE, { sessions: {} });
    db.sessions = db.sessions || {};
    if (db.sessions[normalized]) {
        delete db.sessions[normalized];
        writeJsonSafe(SESSION_STORE_FILE, db);
        return true;
    }
    return false;
}

function resolveCurrentSessionPhone(sock) {
    const candidates = [
        sock?.user?.id,
        sock?.authState?.creds?.me?.id,
        sock?.user?.lid,
        sock?.authState?.creds?.me?.lid
    ];

    for (const candidate of candidates) {
        const phone = normalizePhone(candidate);
        if (phone) return phone;
    }

    return '';
}

async function clearSessionCommand(sock, chatId, msg) {
    try {
        const senderId = msg.key.participant || msg.key.remoteJid;
        const isOwner = await isOwnerOrSudo(senderId, sock, chatId);

        if (!msg.key.fromMe && !isOwner) {
            await sock.sendMessage(chatId, {
                text: '❌ This command can only be used by the owner!',
                ...channelInfo
            });
            return;
        }

        const phone = resolveCurrentSessionPhone(sock);
        if (!phone) {
            await sock.sendMessage(chatId, {
                text: '❌ تعذر تحديد رقم الجلسة الحالية من الاتصال النشط.',
                ...channelInfo
            });
            return;
        }

        await sock.sendMessage(chatId, {
            text: `🔍 جاري حذف جلسة الرقم ${phone} بالكامل من التخزين المحلي وMongoDB...`,
            ...channelInfo
        });

        const files = listMongoSessionJsonFiles(phone);
        const appStateSyncCount = files.filter((file) => file.startsWith('app-state-sync-')).length;
        const preKeyCount = files.filter((file) => file.startsWith('pre-key-')).length;
        const senderKeyCount = files.filter((file) => file.startsWith('sender-key-')).length;
        const signalSessionCount = files.filter((file) => file.startsWith('session-')).length;

        const removedAuthFiles = clearMongoSessionAuthFiles(phone, {
            preserveSessionMeta: false,
            preservePhoneSettings: false,
            ownerId: ''
        });
        const deletedSnapshot = await deleteMongoSessionSnapshot(phone);
        const deletedSessionDir = removeSessionDirectory(phone);
        const deletedSessionStoreRecord = removeSessionStoreRecord(phone);
        const deletedUsersLink = removePhoneFromUsers(phone);
        const deletedPhoneSettings = removePhoneSettings(phone);
        let deletedRemotePhoneSettings = false;
        try {
            deletedRemotePhoneSettings = await deleteRemotePhoneSettings(phone);
        } catch (_) {}

        try { await sock.logout?.(); } catch (_) {}

        const message = `✅ تم حذف جلسة الرقم نهائياً!\n\n` +
            `📱 الرقم: ${phone}\n` +
            `📊 تفاصيل الحذف:\n` +
            `• ملفات auth المحذوفة: ${removedAuthFiles}\n` +
            `• App state sync: ${appStateSyncCount}\n` +
            `• Pre-key: ${preKeyCount}\n` +
            `• Sender-key: ${senderKeyCount}\n` +
            `• Signal sessions: ${signalSessionCount}\n` +
            `• حذف Snapshot البعيد: ${deletedSnapshot ? 'yes' : 'no / already missing'}\n` +
            `• حذف مجلد الجلسة: ${deletedSessionDir ? 'yes' : 'no'}\n` +
            `• حذف سجل session-store: ${deletedSessionStoreRecord ? 'yes' : 'no'}\n` +
            `• حذف الربط من users.json: ${deletedUsersLink ? 'yes' : 'no'}\n` +
            `• حذف إعدادات الرقم: ${deletedPhoneSettings ? 'yes' : 'no'}\n` +
            `• حذف إعدادات الرقم من MongoDB: ${deletedRemotePhoneSettings ? 'yes' : 'no / already missing'}\n` +
            `• Storage mode: Local + MongoDB`;

        await sock.sendMessage(chatId, {
            text: message,
            ...channelInfo
        });
    } catch (error) {
        console.error('Error in clearsession command:', error);
        await sock.sendMessage(chatId, {
            text: '❌ Failed to clear session records completely!',
            ...channelInfo
        });
    }
}

module.exports = clearSessionCommand;
