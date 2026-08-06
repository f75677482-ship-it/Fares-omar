const { AsyncLocalStorage } = require('async_hooks');

const baseSettings = {
  packname: 'Knight Bot',
  author: '‎',
  botName: 'Knight Bot',
  botOwner: 'Professor', // غيّر الاسم كما تريد
  ownerNumber: '919876543210', // غيّر الرقم بدون + وبدون مسافات
  giphyApiKey: 'qnl7ssQChTdPjsKta2Ax2LMaGXz303tq',
  commandMode: 'public',
  maxStoreMessages: 10,
  storeWriteInterval: 10000,
  description: 'بوت واتساب لإدارة المجموعات والتحميل من السوشل ميديا والذكاء الاصطناعي.',
  version: '3.0.8',
  repoUrl: 'https://t.me/Faresw_bot',
  channelLink: 'https://whatsapp.com/channel/0029Vb8jjfWCRs1sVz0x1w3v',
  updateZipUrl: 'https://github.com/faresjahsh/Knightbot-MD/archive/refs/heads/main.zip',
};

const settingsContext = new AsyncLocalStorage();

function getScopedValue(key) {
  const scoped = settingsContext.getStore();
  if (scoped && Object.prototype.hasOwnProperty.call(scoped, key)) {
    return scoped[key];
  }
  return baseSettings[key];
}

const settings = {};

for (const key of Object.keys(baseSettings)) {
  Object.defineProperty(settings, key, {
    enumerable: true,
    configurable: true,
    get() {
      return getScopedValue(key);
    },
    set(value) {
      baseSettings[key] = value;
    }
  });
}

Object.defineProperty(settings, '__baseSettings', {
  enumerable: false,
  configurable: false,
  get() {
    return baseSettings;
  }
});

Object.defineProperty(settings, '__runWithContext', {
  enumerable: false,
  configurable: false,
  writable: false,
  value(context = {}, task = async () => undefined) {
    const current = settingsContext.getStore() || {};
    const next = { ...current, ...(context || {}) };
    return settingsContext.run(next, task);
  }
});

module.exports = settings;
