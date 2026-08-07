/* eslint-disable */
/*
 * lib/inBotSettingsBridge.js
 *
 * بوت الربط يعتمد كلياً على تيليجرام بدون الحاجة إلى موقع ربط خارجي.
 *
 * يدعم الأوامر التالية التي يستجيب لها الرقم المربوط داخل واتساب (DM / رسائل محفوظة):
 *   .section                  عرض الإعدادات العامة
 *   .section general          عرض الإعدادات العامة
 *   .section automation       عرض إعدادات التشغيل التلقائي
 *   .section protection       عرض إعدادات الحماية
 *   .toggle <field> on/off    تشغيل/إيقاف ميزة
 *   .set <field> <value>      تعيين قيمة (رسالة مخصصة، إيموجيات الحالة، …)
 *   .bot / .panel / .اعدادات  عرض قائمة الأوامر
 *
 * يتم حفظ إعدادات كل رقم بشكل مستقل داخل:
 *   data/phone-profiles/<phone>.json
 * مع مزامنة القيم إلى ملفات data/ القديمة دوماً حتى يستمر عمل بقية الكود.
 *
 * كل أمر يستجيب لمالك الرقم فقط — أي شخص آخر يرسل أي أمر فيتم تجاهله بصمت.
 */
'use strict';

const fs = require('fs');
const path = require('path');

const PROJECT_ROOT = process.cwd();
const DATA_DIR = path.join(PROJECT_ROOT, 'data');
const PHONE_PROFILES_DIR = path.join(DATA_DIR, 'phone-profiles');
const PHONE_SETTINGS_DB_FILE = path.join(PROJECT_ROOT, 'phone-settings.json');

function ensureDir(p) {
    if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true });
}
ensureDir(PHONE_PROFILES_DIR);
ensureDir(DATA_DIR);

function normalizePhone(value) {
    return String(value || '').replace(/\D/g, '').trim();
}

function readJsonSafe(file, fallback) {
    try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch (_) { return fallback; }
}

function writeJsonAtomic(file, value) {
    try {
        ensureDir(path.dirname(file));
        fs.writeFileSync(file, JSON.stringify(value, null, 2));
        return true;
    } catch (e) {
        console.error('inBotSettingsBridge.writeJsonAtomic', file, e?.message || e);
        return false;
    }
}

function profilePath(phone) {
    return path.join(PHONE_PROFILES_DIR, `${normalizePhone(phone)}.json`);
}

const DEFAULT_PROFILE = {
    name: 'Golden Queen Bot',
    ownername: 'Golden Queen Bot',
    ownerNumber: '',
    description: 'بوت واتساب متصل عبر بوت تيليجرام — جميع الإعدادات تتم من داخل البوت.',
    from: 'Yemen',
    age: '24',
    prefix: '.',
    footer2: 'Golden Queen Bot',
    mode: 'public',
    antiBad: 'off',
    antiLink: 'off',
    autoRecording: 'off',
    autoTyping: 'off',
    alwaysOnline: 'off',
    autoStatusRead: 'on',
    autoStatusReact: 'on',
    statusReactionNotice: 'on',
    autoPrivateReact: 'off',
    ghostMode: 'off',
    autoRead: 'off',
    autoBlock: 'off',
    autoReact: 'off',
    autoVoice: 'off',
    antiDelete: 'off',
    sendDeleteTo: 'owner',
    antiCall: 'off',
    excludeCallNumbers: '',
    statusMsgSend: 'off',
    statusMsgType: 'default',
    customMsg: '',
    statusCustomReact: '❤️,🔥,😍',
    menu: '',
    alive: '',
    owner: '',
    antiBug: 'off',
    antiBot: 'off',
    antiBotAction: 'delete',
    gaGroupJid: '',
    gaTimezone: 'Asia/Aden',
    gaCloseTime: '15:00',
    gaOpenTime: '05:00',
    language: 'arabic',
    antiViewOnce: 'off',
    antiLinkList: 'wa.me,whatsapp.com',
    antiBadWords: '',
    antiMention: 'off',
    antiEdit: 'off',
    antiAction: 'wern',
    antiWarnCount: '3',
    autoReactScope: 'inbox',
    aiReplyScope: 'inbox',
    aliveMsg: '✅ البوت شغال الآن',
    voiceFooter: '',
    updatedAt: null
};

function loadProfile(phone) {
    const file = profilePath(phone);
    const stored = readJsonSafe(file, {});
    const merged = { ...DEFAULT_PROFILE, ...(stored || {}) };
    merged.ownerNumber = normalizePhone(merged.ownerNumber || phone);
    merged.updatedAt = merged.updatedAt || new Date().toISOString();
    return merged;
}

function saveProfile(phone, profile) {
    const safe = { ...DEFAULT_PROFILE, ...(profile || {}), updatedAt: new Date().toISOString() };
    return writeJsonAtomic(profilePath(phone), safe);
}

// Mirror to legacy JSON files used by older code paths so both worlds stay consistent.
function mirrorLegacy(profile) {
    try {
        const autoStatus = readJsonSafe(path.join(DATA_DIR, 'autoStatus.json'), { global: 'off', groups: {}, enabled: false, reactOn: false });
        autoStatus.global = profile.autoStatusRead === 'on' ? 'on' : 'off';
        autoStatus.enabled = profile.autoStatusRead === 'on';
        autoStatus.reactOn = profile.autoStatusReact === 'on';
        writeJsonAtomic(path.join(DATA_DIR, 'autoStatus.json'), autoStatus);

        const autoread = readJsonSafe(path.join(DATA_DIR, 'autoread.json'), { global: 'off', chats: {}, enabled: false });
        autoread.global = profile.autoRead === 'on' ? 'on' : 'off';
        autoread.enabled = profile.autoRead === 'on';
        writeJsonAtomic(path.join(DATA_DIR, 'autoread.json'), autoread);

        const autotyping = readJsonSafe(path.join(DATA_DIR, 'autotyping.json'), { global: 'off', chats: {}, enabled: false });
        autotyping.global = profile.autoTyping === 'on' ? 'on' : 'off';
        autotyping.enabled = profile.autoTyping === 'on';
        writeJsonAtomic(path.join(DATA_DIR, 'autotyping.json'), autotyping);

        const mode = readJsonSafe(path.join(DATA_DIR, 'messageCount.json'), { isPublic: true, messageCount: {} });
        mode.isPublic = profile.mode === 'public';
        writeJsonAtomic(path.join(DATA_DIR, 'messageCount.json'), mode);
    } catch (e) {
        console.error('inBotSettingsBridge.mirrorLegacy', e?.message || e);
    }
}

function isOwnerJidForNumber({ senderJid, chatId, phone, fromMe }) {
    if (fromMe === true) return true;
    const phoneClean = normalizePhone(phone);
    if (!phoneClean) return false;
    const senderClean = normalizePhone(senderJid);
    const chatClean = normalizePhone(chatId);
    if (senderClean && senderClean === phoneClean) return true;
    if (chatClean && chatClean === phoneClean) return true;
    return false;
}

function isSelfDm({ chatId, phone }) {
    const phoneClean = normalizePhone(phone);
    if (!phoneClean) return false;
    const chatClean = normalizePhone(chatId);
    return phoneClean === chatClean;
}

function buildSectionText(section, profile) {
    const lines = [];
    const heading = section === 'automation'
        ? 'إعدادات التشغيل التلقائي'
        : section === 'protection'
            ? 'إعدادات الحماية'
            : 'الإعدادات العامة';
    lines.push('╭──〔 ⚙️ ' + heading + ' 〕──╮');

    const safe = (s) => String(s == null ? '—' : s);

    const rows = section === 'automation'
        ? [
            ['👁️ قراءة الحالات', profile.autoStatusRead],
            ['💬 التفاعل على الحالات', profile.autoStatusReact],
            ['🪄 إشعار التفاعل', profile.statusReactionNotice],
            ['🙈 وضع الشبح', profile.ghostMode],
            ['🏠 الرد التلقائي للخاص', profile.autoPrivateReact],
            ['📖 قراءة تلقائية', profile.autoRead],
            ['⌨️ كتابة تلقائية', profile.autoTyping],
            ['🟢 متصل دائماً', profile.alwaysOnline],
            ['🎛️ وضع البوت', profile.mode === 'public' ? 'عام' : 'خاص'],
            ['🚀 رسالة الحالة', safe(profile.customMsg)],
            ['😍 رموز التفاعل', safe(profile.statusCustomReact)]
        ]
        : section === 'protection'
            ? [
                ['🛡️ مكافحة الكلمات السيئة', profile.antiBad],
                ['🔗 مكافحة الروابط', profile.antiLink],
                ['🚫 مكافحة الاتصال', profile.antiCall],
                ['🗑️ مكافحة الحذف', profile.antiDelete],
                ['🤖 مكافحة البوتات', profile.antiBot],
                ['🐞 مكافحة البق', profile.antiBug],
                ['🔁 منع تعديل الرسائل', profile.antiEdit],
                ['🚷 منع المنشن', profile.antiMention],
                ['👁️‍🗨️ منع عرض مرة واحدة', profile.antiViewOnce]
            ]
            : [
                ['🤖 اسم البوت', safe(profile.name)],
                ['👤 اسم المالك', safe(profile.ownername)],
                ['📞 رقم التواصل', safe(profile.ownerNumber)],
                ['🌍 الموقع', safe(profile.from)],
                ['🎂 العمر', safe(profile.age)],
                ['🔧 البادئة', safe(profile.prefix)],
                ['📝 الوصف', safe(profile.description)]
            ];

    for (const [k, v] of rows) {
        lines.push(`│ ${k}: ${v}`);
    }

    lines.push('╰────────────────────╯');
    lines.push('');
    lines.push('🛠️ أمثلة:');
    lines.push('• .toggle autoStatusRead on');
    lines.push('• .toggle ghost off');
    lines.push('• .set customMsg رسالة مخصصة');
    lines.push('• .set statusCustomReact 😍 ❤️ 🔥');
    return lines.join('\n');
}

const FIELD_ALIASES = Object.create(null);
[
    ['autostatus', 'autoStatusRead'],
    ['autostatusread', 'autoStatusRead'],
    ['statusread', 'autoStatusRead'],
    ['autostatusreact', 'autoStatusReact'],
    ['statusreact', 'autoStatusReact'],
    ['react', 'autoStatusReact'],
    ['statusmessage', 'customMsg'],
    ['custommsg', 'customMsg'],
    ['statuscustomreact', 'statusCustomReact'],
    ['customreact', 'statusCustomReact'],
    ['ghosthint', 'ghostMode'],
    ['ghost', 'ghostMode'],
    ['mode', 'mode'],
    ['public', 'mode'],
    ['private', 'autoPrivateReact'],
    ['autoprivate', 'autoPrivateReact'],
    ['autoprivatereact', 'autoPrivateReact'],
    ['autoread', 'autoRead'],
    ['autotyping', 'autoTyping'],
    ['alwaysonline', 'alwaysOnline'],
    ['autoreact', 'autoReact'],
    ['autoblock', 'autoBlock'],
    ['autovoice', 'autoVoice'],
    ['anticall', 'antiCall'],
    ['antidelete', 'antiDelete'],
    ['antibad', 'antiBad'],
    ['antilink', 'antiLink'],
    ['antibug', 'antiBug'],
    ['antibot', 'antiBot'],
    ['antimention', 'antiMention'],
    ['antiviewonce', 'antiViewOnce'],
    ['autorecording', 'autoRecording'],
    ['statusmsgsend', 'statusMsgSend'],
    ['statusmsgtype', 'statusMsgType'],
    ['statusreactionnotice', 'statusReactionNotice'],
    ['senddeleteto', 'sendDeleteTo'],
    ['language', 'language']
].forEach(([alias, canonical]) => { FIELD_ALIASES[alias] = canonical; });

function resolveFieldAlias(token) {
    return FIELD_ALIASES[String(token || '').toLowerCase()] || null;
}

function onOffValue(v) {
    const s = String(v || '').toLowerCase().trim();
    if (['on', 'تشغيل', 'شغل', 'تفعيل', 'enable', 'enabled', '1', 'true', 'نعم', 'مفعّل', 'مفعل'].includes(s)) return 'on';
    if (['off', 'ايقاف', 'إيقاف', 'تعطيل', 'disable', 'disabled', '0', 'false', 'لا', 'معطّل', 'معطل'].includes(s)) return 'off';
    return null;
}

function getPhoneSettingsPasswordEntry(phone) {
    const normalizedPhone = normalizePhone(phone);
    if (!normalizedPhone) return null;

    const db = readJsonSafe(PHONE_SETTINGS_DB_FILE, { profiles: {} });
    const profile = db?.profiles?.[normalizedPhone] || null;
    if (!profile || typeof profile !== 'object') return null;

    const activeAppId = String(profile.activeAppId || 'default').trim() || 'default';
    const credentials = profile.credentials || {};
    const preferredCredential = credentials[activeAppId] || credentials.default || Object.values(credentials).find((item) => String(item?.password || '').trim());
    const password = String(preferredCredential?.password || '').trim();
    if (!password) return null;

    return {
        phone: normalizedPhone,
        appId: activeAppId,
        password
    };
}

function buildPhonePasswordMessage(phone) {
    const credential = getPhoneSettingsPasswordEntry(phone);
    if (!credential) {
        return '⌛ باسورد الرقم غير جاهز حالياً. جرّب بعد ثوانٍ قليلة من نجاح الربط.';
    }

    return [
        `🔐 باسورد الرقم ${credential.phone}`,
        '',
        `📱 الرقم: ${credential.phone}`,
        `🗝️ كلمة السر: ${credential.password}`,
        '',
        '⚠️ احتفظ بها ولا تشاركها مع أي شخص.'
    ].join('\n');
}

function buildPanelMessage(panelType) {
    const lines = [
        '╭──〔 📜 قائمة الأوامر 〕──╮',
        '│',
        '│ .section general',
        '│ عرض الإعدادات العامة',
        '│',
        '│ .section automation',
        '│ عرض إعدادات التشغيل التلقائي',
        '│',
        '│ .toggle autoStatusRead on/off',
        '│ تشغيل أو إيقاف قراءة الحالات',
        '│',
        '│ .toggle autoStatusReact on/off',
        '│ تشغيل أو إيقاف التفاعل على الحالات',
        '│',
        '│ .toggle ghost on/off',
        '│ تشغيل أو إيقاف وضع الشبح',
        '│',
        '│ .toggle private on/off',
        '│ تشغيل أو إيقاف الرد التلقائي للخاص',
        '│',
        '│ .set customMsg نص الرسالة',
        '│ تعيين رسالة تلقائية مخصصة',
        '│',
        '│ .set statusCustomReact 😍 ❤️ 🔥',
        '│ تعيين إيموجيات التفاعل',
        '│',
        '│ .bsord',
        '│ يرسل باسورد الرقم المربوط',
        '│',
        '╰────────────────────╯',
        '',
        '⚙️ جميع إعدادات الرقم تتم من داخل البوت فقط.',
        '🔒 كل الأوامر تستجيب لمالك الرقم فقط.'
    ];
    return lines.join('\n');
}

async function handleInBotSettingsCommand({ sock, phoneNumber, msg }) {
    try {
        if (!sock || !msg || !msg.message) return false;

        const text = String(
            msg?.message?.conversation ||
            msg?.message?.extendedTextMessage?.text ||
            msg?.message?.imageMessage?.caption ||
            msg?.message?.videoMessage?.caption ||
            ''
        ).trim();
        if (!text) return false;
        if (!text.startsWith('.')) return false;

        const parts = text.replace(/^\.\s*/, '').split(/\s+/);
        const cmd = (parts.shift() || '').toLowerCase();

        const SUPPORTED = new Set([
            'section', 'toggle', 'set', 'bsord',
            'سيت', 'توجال', 'سكيشن',
            'القائمة', 'اعدادات', 'إعدادات',
            'bot', 'لوحة', 'panel', 'اعداد', 'الإعدادات'
        ]);
        if (!SUPPORTED.has(cmd)) return false;

        const phone = normalizePhone(phoneNumber);
        if (!phone) return false;

        const chatId = msg?.key?.remoteJid || '';
        const senderId = msg?.key?.participant || msg?.key?.remoteJid || '';

        // Always respond for self DM (owner talking to themselves / saved messages).
        // For incoming messages, owner must equal the linked phone itself.
        const ownerCheck = isOwnerJidForNumber({
            senderJid: senderId,
            chatId: chatId,
            phone,
            fromMe: msg?.key?.fromMe === true
        });
        if (!ownerCheck) {
            // Owner gate: silently swallow for anyone else (don't leak anything).
            return true;
        }

        let profile = loadProfile(phone);

        if (cmd === 'bsord') {
            await sock.sendMessage(chatId, { text: buildPhonePasswordMessage(phone) }, { quoted: msg });
            return true;
        }

        if (cmd === 'section' || cmd === 'سكيشن') {
            let section = (parts[0] || 'general').toLowerCase();
            if (['الإعداداتالعامة', 'العامة', 'general', 'الاعداداتالعامة', 'الاعدادات', 'إعدادات'].includes(section)) section = 'general';
            else if (['التشغيلالتلقائي', 'التلقائي', 'التشغيل', 'automation'].includes(section)) section = 'automation';
            else if (['الحماية', 'protection'].includes(section)) section = 'protection';
            await sock.sendMessage(chatId, { text: buildSectionText(section, profile) }, { quoted: msg });
            return true;
        }

        if (cmd === 'toggle' || cmd === 'توجال') {
            const rawAlias = (parts[0] || '').toLowerCase();
            const onOff = onOffValue(parts[1] || '');
            if (!rawAlias || !onOff) {
                await sock.sendMessage(chatId, {
                    text: '❌ الاستخدام: .toggle <الميزة> on/off\nمثال:\n.toggle ghost on\n.toggle autoStatusRead off\n.toggle private on'
                }, { quoted: msg });
                return true;
            }

            const canonical = resolveFieldAlias(rawAlias);
            let displayLabel = rawAlias;

            if (rawAlias === 'public' || rawAlias === 'mode') {
                profile.mode = onOff === 'on' ? 'public' : 'private';
                displayLabel = 'وضع البوت';
            } else if (canonical === 'autoPrivateReact' || rawAlias === 'private' || rawAlias === 'خاص') {
                profile.autoPrivateReact = onOff;
                displayLabel = 'الرد التلقائي للخاص';
            } else if (canonical && canonical in profile) {
                profile[canonical] = onOff;
                displayLabel = canonical;
            } else {
                await sock.sendMessage(chatId, { text: '❌ الميزة غير معروفة: ' + rawAlias + '\nجرّب: .toggle ghost on' }, { quoted: msg });
                return true;
            }

            saveProfile(phone, profile);
            mirrorLegacy(profile);
            await sock.sendMessage(chatId, {
                text: `✅ تم تغيير ${displayLabel} إلى ${onOff.toUpperCase()}`
            }, { quoted: msg });
            return true;
        }

        if (cmd === 'set' || cmd === 'سيت') {
            if (parts.length < 1) {
                await sock.sendMessage(chatId, {
                    text: '❌ الاستخدام: .set <الحقل> <القيمة>\nمثال:\n.set customMsg مرحبا فيكم\n.set statusCustomReact 😍 ❤️ 🔥'
                }, { quoted: msg });
                return true;
            }
            const alias = (parts.shift() || '').toLowerCase();
            const value = parts.join(' ').trim();

            if (alias === 'statuscustomreact' || alias === 'customreact' || alias === 'react') {
                const emojis = value.split(/[\s,،]+/).filter(Boolean).slice(0, 10);
                profile.statusCustomReact = emojis.length ? emojis.join(' ') : value;
                saveProfile(phone, profile);
                await sock.sendMessage(chatId, { text: '✅ تم تحديث إيموجيات التفاعل:\n' + profile.statusCustomReact }, { quoted: msg });
                return true;
            }

            if (alias === 'custommsg' || alias === 'statusmsg' || alias === 'message') {
                profile.customMsg = value;
                saveProfile(phone, profile);
                mirrorLegacy(profile);
                await sock.sendMessage(chatId, { text: '✅ تم تحديث رسالة الحالة المخصصة:\n' + value }, { quoted: msg });
                return true;
            }

            if (alias === 'mode') {
                if (!['public', 'private', 'عام', 'علني', 'خاص'].includes(value.toLowerCase())) {
                    await sock.sendMessage(chatId, { text: '❌ القيمة يجب أن تكون public أو private' }, { quoted: msg });
                    return true;
                }
                profile.mode = (value.toLowerCase() === 'public' || value === 'عام' || value === 'علني') ? 'public' : 'private';
                saveProfile(phone, profile);
                mirrorLegacy(profile);
                await sock.sendMessage(chatId, { text: '✅ تم تحديث وضع البوت إلى: ' + (profile.mode === 'public' ? 'عام' : 'خاص') }, { quoted: msg });
                return true;
            }

            if (alias === 'name' || alias === 'botname') {
                profile.name = value.slice(0, 32);
            } else if (alias === 'ownername' || alias === 'owner') {
                profile.ownername = value.slice(0, 40);
            } else if (alias === 'from') {
                profile.from = value;
            } else if (alias === 'age') {
                profile.age = String(parseInt(value, 10) || value);
            } else if (alias === 'prefix' || alias === 'بادئة') {
                profile.prefix = value.slice(0, 3);
            } else if (alias === 'footer' || alias === 'footer2') {
                profile.footer2 = value.slice(0, 60);
            } else if (alias === 'description') {
                profile.description = value.slice(0, 240);
            } else if (alias === 'aliveMsg') {
                profile.aliveMsg = value;
            } else if (alias === 'voiceFooter') {
                profile.voiceFooter = value;
            } else if (alias === 'language') {
                profile.language = value;
            } else if (alias === 'excludenumbers' || alias === 'excludecallnumbers') {
                profile.excludeCallNumbers = value;
            } else if (alias === 'antibadwords' || alias === 'antibadlist') {
                profile.antiBadWords = value;
            } else if (alias === 'antilinklist') {
                profile.antiLinkList = value;
            } else {
                await sock.sendMessage(chatId, { text: '❌ الحقل غير مدعوم: ' + alias + '\nالحقول المدعومة: customMsg, statusCustomReact, mode, name, owner, from, age, prefix, footer, description, excludeCallNumbers' }, { quoted: msg });
                return true;
            }

            saveProfile(phone, profile);
            mirrorLegacy(profile);
            await sock.sendMessage(chatId, { text: '✅ تم تحديث ' + alias + ' بنجاح.\n📌 القيمة الجديدة: ' + value }, { quoted: msg });
            return true;
        }

        if (cmd === 'bot' || cmd === 'لوحة' || cmd === 'panel' || cmd === 'اعدادات' || cmd === 'إعدادات' || cmd === 'القائمة' || cmd === 'الاعدادات') {
            await sock.sendMessage(chatId, { text: buildPanelMessage('bot') }, { quoted: msg });
            return true;
        }

        return false;
    } catch (e) {
        console.error('inBotSettingsBridge.handle', e?.message || e);
        return false;
    }
}

module.exports = {
    handleInBotSettingsCommand,
    isOwnerJidForNumber,
    isSelfDm,
    loadProfile,
    saveProfile,
    DEFAULT_PROFILE,
    PHONE_PROFILES_DIR,
    buildSectionText,
    buildPanelMessage,
    FIELD_ALIASES,
    onOffValue,
    resolveFieldAlias,
    getPhoneSettingsPasswordEntry,
    buildPhonePasswordMessage
};
