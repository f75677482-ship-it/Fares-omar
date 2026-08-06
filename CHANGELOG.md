# Fares-omar — In-bot linking & per-session persistence

## المشكلة
- ربط رقم جديد كان يفصل الرقم السابق (singleton socket).
- كل رقم يخزن إعداداته في ملف واحد مشترك (`settings.json`).
- أوامر `.section / .toggle / .set` التي يفترض أن يستجيب لها الرقم المربوط (DM لنفسه) لم تكن تستجيب.

## الحل
1. **بوت تيليجرام فقط للربط** — لم تعد هناك حاجة لموقع ربط خارجي.
   - `/pair <phone>` يطلب كود اقتران Baileys ويُرسله عبر تيليجرام.
   - على كل ربط جديد، تُحفظ الـcredentials في مجلد مستقل:
     `sessions/<phone>/creds.json + app-state-sync-*`.
   - الـWatchdog في `server.js` و `index.js` يعيد تشغيل جميع الجلسات المحفوظة على بدء التشغيل.
2. **جلسات منفصلة لكل رقم** — اعتماداً على منطق `lib/sessionManager.js`
   و `lib/pairingBridge.js` الموجود أصلاً (مع مفتاح الخريطة = رقم الهاتف).
3. **إعدادات مستقلة لكل رقم** — ملف جديد:
     `lib/inBotSettingsBridge.js`
   - يحفظ كل إعدادات الرقم في: `data/phone-profiles/<phone>.json`.
   - يعكس التغييرات على ملفات `data/autoStatus.json`, `data/autoread.json`, `data/autotyping.json`,
     `data/messageCount.json` ليبقى بقية الكود يعمل بنفس الشكل.
4. **تفعيل أوامر الرقم نفسه** — `lib/legacyCommandBridge.js` يعترض أوامر
   `.section / .toggle / .set / .bot / .اعدادات` قبل تسليمها إلى الـdispatcher القديم
   ويستجيب لها فقط عندما يكون المرسل هو **مالك الرقم المربوط** (نفس الـJID أو `fromMe` أو رسالة محفوظة لنفسه).
5. رد الأمر يُرسل دائماً ضمن بوت الواتساب إلى نفس الدردشة التي وصل منها الأمر،
   مما يجعل الإعدادات تتم من **داخل البوت فقط**.

## الأوامر المدعومة (داخل الرقم المربوط)
| الأمر | الوظيفة |
|---|---|
| `.bot` / `.اعدادات` / `.panel` | عرض قائمة الأوامر المنسقة |
| `.section general` | عرض الإعدادات العامة |
| `.section automation` | عرض إعدادات التشغيل التلقائي |
| `.section protection` | عرض إعدادات الحماية |
| `.toggle autoStatusRead on/off` | تشغيل/إيقاف قراءة الحالات |
| `.toggle autoStatusReact on/off` | تشغيل/إيقاف التفاعل على الحالات |
| `.toggle ghost on/off` | تشغيل/إيقاف وضع الشبح |
| `.toggle private on/off` | تشغيل/إيقاف الرد التلقائي للخاص |
| `.toggle autoRead on/off` | قراءة تلقائية |
| `.toggle autoTyping on/off` | كتابة تلقائية |
| `.toggle mode public/private` | وضع البوت |
| `.set customMsg <نص>` | تعيين رسالة الحالة المخصصة |
| `.set statusCustomReact 😍 ❤️ 🔥` | تعيين إيموجيات التفاعل |

## بوابة المالك
- كل أمر يستجيب **فقط للمالك**:
  - رسالة محفوظة للنفس (self-DM JID = رقمه) أو
  - `fromMe === true` أو
  - JID المرسل = رقمه المربوط.
- أي شخص آخر يرسل هذه الأوامر فيتم تجاهلها بصمت (لا رد ولا اعتراف).

## الملفات المعدّلة في هذه الحزمة
1. `lib/inBotSettingsBridge.js` — جديد (258 سطر): المنطق الكامل لحفظ/تعديل الإعدادات والاستجابة للأوامر مع بوابة المالك.
2. `lib/legacyCommandBridge.js` — تعديل: إضافة استدعاء `handleInBotSettingsCommand` قبل الـdispatcher القديم للأوامر `.section/.toggle/.set/.bot`.

## تمرير الـsyntax
كل الملفات تمرّ بـ`node -c` بدون أخطاء.

## خطوات التطبيق
```bash
unzip fares-omar-patch.zip
cp lib/inBotSettingsBridge.js   <repo>/lib/
cp lib/legacyCommandBridge.js   <repo>/lib/
npm install   # إذا لزم
node index.js
```
