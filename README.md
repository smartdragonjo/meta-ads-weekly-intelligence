# Meta Ads Weekly Intelligence

هذا المشروع يقرأ ملفات CSV الأسبوعية من `imports/current/`، يدمجها في تقرير أسبوعي فوري، ويُحدث `docs/data/latest.json` بدون أي تراكم تاريخي. التقرير الحالي يمثل الحالة الكاملة لهذا الأسبوع فقط.

## مكان رفع CSV

ضع ملفات CSV الجديدة داخل:

`imports/current/`

كل أسبوع يتم حذف CSV السابق في GitHub ثم رفع CSV الحالي ضمن نفس المجلد. لا يعتمد المشروع على عدد ثابت من الملفات.

## التشغيل الأسبوعي

```powershell
python -m meta_ads_intelligence.weekly_pipeline --input-dir imports/current --latest-json docs/data/latest.json
```

إذا لم يجد أي CSV في `imports/current/`, يوقف التشغيل دون مسح `latest.json` الحالي.

## Dashboard Read-only

الواجهة الحالية داخل `docs/` تبقى للقراءة فقط. لا توجد Upload أو File input أو أي إدخال مستخدم لتعديل البيانات. كل رفع CSV يتم من GitHub فقط، والتشغيل الخارجي لـ Cloud Run من GitHub Actions فقط.

## تحليل الفيديو

إذا كانت إعلانات الفيديو الجديدة غير موجودة في `data/video-analysis-cache.json`, يمكن إرسال دفعة واحدة إلى Cloud Run Job `competitors-report` عبر GitHub Actions. لا يتم إنشاء Job جديد، ولا يتم استخدام أي AI API جديد داخل هذا المستودع.

## متغيرات GitHub / Google Cloud

إعدادات Google Cloud التي يمكن تكوينها عبر Repository Variables / Secrets:

- `CLOUD_RUN_PROCESSING_ENABLED`
- `GCP_PROJECT_ID`
- `GCP_REGION`
- `CLOUD_RUN_JOB_NAME` (افتراضي `competitors-report`)
- `FIRESTORE_PROJECT_ID`
- `META_ADS_RESULT_COLLECTION` (افتراضي `meta_ads_processing_results`)
- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_SERVICE_ACCOUNT`

لا يتم تخزين أي Secret داخل `docs/` أو `latest.json`.

## Firebase Authentication

واجهة GitHub Pages لا تتغير في منطق Firebase Authentication. قائمة المستخدمين المسموحين تبقى داخل `docs/js/firebase-config.js` ضمن `ALLOWED_EMAILS`, وتُدار كما كان سابقًا.

## الاختبارات

```powershell
python -m unittest discover -s tests -v
```
