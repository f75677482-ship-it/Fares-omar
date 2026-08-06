// isAdmin.js
const GROUP_CACHE_TTL_MS = Math.max(1500, Number(process.env.GROUP_METADATA_CACHE_MS || 5000));
const groupMetadataCache = new Map();

function normalizeNumeric(value = '') {
    return String(value || '').split('@')[0].split(':')[0].replace(/\D/g, '');
}

function buildCandidateSet(...values) {
    const set = new Set();
    for (const value of values) {
        const raw = String(value || '').trim();
        if (!raw) continue;
        set.add(raw);
        set.add(raw.split('@')[0]);
        set.add(raw.split('@')[0].split(':')[0]);
        const numeric = normalizeNumeric(raw);
        if (numeric) set.add(numeric);
    }
    return set;
}

function hasIntersection(left, right) {
    for (const value of left) {
        if (right.has(value)) return true;
    }
    return false;
}

function extractParticipants(metadata = {}) {
    return Array.isArray(metadata?.participants) ? metadata.participants : [];
}

async function getGroupMetadataCached(sock, chatId) {
    const key = String(chatId || '').trim();
    const now = Date.now();
    const cached = groupMetadataCache.get(key);
    if (cached && now - cached.fetchedAt < GROUP_CACHE_TTL_MS) {
        return cached.metadata;
    }

    const metadata = await sock.groupMetadata(chatId);
    groupMetadataCache.set(key, { metadata, fetchedAt: now });
    return metadata;
}

function isParticipantAdmin(participant = {}) {
    return participant?.admin === 'admin' || participant?.admin === 'superadmin';
}

function matchParticipant(participant = {}, targetCandidates) {
    const participantCandidates = buildCandidateSet(
        participant?.id,
        participant?.jid,
        participant?.lid,
        participant?.phoneNumber,
        participant?.pn,
        participant?.user
    );
    return hasIntersection(participantCandidates, targetCandidates);
}

async function isAdmin(sock, chatId, senderId) {
    try {
        const metadata = await getGroupMetadataCached(sock, chatId);
        const participants = extractParticipants(metadata);
        const botCandidates = buildCandidateSet(sock?.user?.id, sock?.user?.jid, sock?.user?.lid);
        const senderCandidates = buildCandidateSet(senderId);

        const isBotAdmin = participants.some((participant) => matchParticipant(participant, botCandidates) && isParticipantAdmin(participant));
        const isSenderAdmin = participants.some((participant) => matchParticipant(participant, senderCandidates) && isParticipantAdmin(participant));

        return { isSenderAdmin, isBotAdmin };    
    } catch (err) {
        const cached = groupMetadataCache.get(String(chatId || '').trim());
        if (cached?.metadata) {
            try {
                const participants = extractParticipants(cached.metadata);
                const botCandidates = buildCandidateSet(sock?.user?.id, sock?.user?.jid, sock?.user?.lid);
                const senderCandidates = buildCandidateSet(senderId);
                return {
                    isSenderAdmin: participants.some((participant) => matchParticipant(participant, senderCandidates) && isParticipantAdmin(participant)),
                    isBotAdmin: participants.some((participant) => matchParticipant(participant, botCandidates) && isParticipantAdmin(participant))
                };
            } catch (_) {}
        }

        console.error('❌ Error in isAdmin:', err?.message || err);
        return { isSenderAdmin: false, isBotAdmin: false };
    }
}

module.exports = isAdmin;
