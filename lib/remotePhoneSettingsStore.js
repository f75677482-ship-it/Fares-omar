'use strict';

require('dotenv').config();

const { getMongoCollection, isMongoConfigured } = require('./mongoClient');

const COLLECTION_NAME = String(process.env.MONGODB_PHONE_SETTINGS_COLLECTION || 'phone_settings_profiles').trim() || 'phone_settings_profiles';
const ENABLE_REMOTE_PHONE_SETTINGS_STORE = ['1', 'true', 'yes', 'on'].includes(
  String(process.env.ENABLE_REMOTE_PHONE_SETTINGS_STORE || process.env.ENABLE_REMOTE_SESSION_STORE || 'true').trim().toLowerCase()
);

function normalizePhone(phone = '') {
  return String(phone || '').replace(/\D/g, '').trim();
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function isRemotePhoneSettingsStoreEnabled() {
  return ENABLE_REMOTE_PHONE_SETTINGS_STORE && isMongoConfigured();
}

async function getCollection() {
  if (!isRemotePhoneSettingsStoreEnabled()) {
    throw new Error('Remote phone settings store is not configured');
  }

  const collection = await getMongoCollection(COLLECTION_NAME);
  await Promise.allSettled([
    collection.createIndex({ phone: 1 }, { unique: true }),
    collection.createIndex({ updatedAt: -1 }),
  ]);
  return collection;
}

function normalizeProfile(profile = {}) {
  if (!profile || typeof profile !== 'object') {
    return {
      activeAppId: 'default',
      apps: {},
      credentials: {},
    };
  }

  const activeAppId = String(profile.activeAppId || 'default').trim() || 'default';
  const apps = profile.apps && typeof profile.apps === 'object' ? clone(profile.apps) : {};
  const credentials = profile.credentials && typeof profile.credentials === 'object' ? clone(profile.credentials) : {};

  return {
    activeAppId,
    apps,
    credentials,
  };
}

function normalizeDocument(phone, profile = {}, existing = {}) {
  const normalizedPhone = normalizePhone(phone || existing.phone || '');
  if (!normalizedPhone) return null;

  const normalizedProfile = normalizeProfile(profile);
  const now = new Date().toISOString();

  return {
    _id: normalizedPhone,
    phone: normalizedPhone,
    profile: normalizedProfile,
    updatedAt: now,
    createdAt: existing.createdAt || now,
  };
}

async function listRemotePhoneSettings() {
  const collection = await getCollection();
  const items = await collection.find({}, { projection: { _id: 0 } }).sort({ updatedAt: -1, phone: 1 }).toArray();
  return Array.isArray(items)
    ? items
        .map((item) => ({
          phone: normalizePhone(item?.phone || ''),
          profile: normalizeProfile(item?.profile || {}),
          updatedAt: item?.updatedAt || null,
          createdAt: item?.createdAt || null,
        }))
        .filter((item) => item.phone)
    : [];
}

async function fetchRemotePhoneSettings(phone = '') {
  const normalizedPhone = normalizePhone(phone);
  if (!normalizedPhone) return null;
  const collection = await getCollection();
  const item = await collection.findOne({ _id: normalizedPhone }, { projection: { _id: 0 } });
  if (!item) return null;

  return {
    phone: normalizedPhone,
    profile: normalizeProfile(item?.profile || {}),
    updatedAt: item?.updatedAt || null,
    createdAt: item?.createdAt || null,
  };
}

async function upsertRemotePhoneSettings(phone = '', profile = {}) {
  const normalizedPhone = normalizePhone(phone);
  if (!normalizedPhone) return null;

  const collection = await getCollection();
  const existing = await collection.findOne({ _id: normalizedPhone }, { projection: { createdAt: 1, phone: 1 } });
  const normalized = normalizeDocument(normalizedPhone, profile, existing || {});
  if (!normalized) return null;

  await collection.updateOne(
    { _id: normalizedPhone },
    {
      $set: {
        phone: normalized.phone,
        profile: normalized.profile,
        updatedAt: normalized.updatedAt,
      },
      $setOnInsert: {
        createdAt: normalized.createdAt,
      },
    },
    { upsert: true }
  );

  return fetchRemotePhoneSettings(normalizedPhone);
}

async function deleteRemotePhoneSettings(phone = '') {
  const normalizedPhone = normalizePhone(phone);
  if (!normalizedPhone) return false;
  const collection = await getCollection();
  const result = await collection.deleteOne({ _id: normalizedPhone });
  return result.deletedCount > 0;
}

module.exports = {
  isRemotePhoneSettingsStoreEnabled,
  listRemotePhoneSettings,
  fetchRemotePhoneSettings,
  upsertRemotePhoneSettings,
  deleteRemotePhoneSettings,
};
