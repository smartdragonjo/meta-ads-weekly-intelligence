# Meta Ads Weekly Intelligence

هذا المشروع يقرأ ملفات CSV الأسبوعية من `imports/current/`، يدمجها في تقرير أسبوعي فوري، ويُحدث `docs/data/latest.json` بدون أي تراكم تاريخي. التقرير الحالي يمثل الحالة الكاملة لهذا الأسبوع فقط.

## مكان رفع CSV

ضع ملفات CSV الجديدة داخل:

`imports/current/`

كل أسبوع استبدل ملفات CSV السابقة بملفات الأسبوع الحالي ضمن نفس المجلد. تُقرأ ملفات `imports/current/*.csv` فقط، بالترتيب الأبجدي لأسماء الملفات، ويُحتفظ بآخر سجل لكل `ad_id` مع تجاهل المعرّفات الفارغة. لا يعتمد المشروع على عدد ثابت من الملفات ولا يقرأ `archive/history.json` في المسار الأسبوعي.

## التشغيل الأسبوعي

```powershell
python -m meta_ads_intelligence.weekly_pipeline --input-dir imports/current --latest-json docs/data/latest.json
```

المسار الافتراضي هو `imports/current`، لذلك يكفي أيضًا `python -m meta_ads_intelligence.weekly_pipeline`. إذا لم يجد CSV أو لم يجد أي `ad_id` صالح، يخرج برمز فشل دون مسح `latest.json` أو إنشاء تقرير فارغ.

هذا التشغيل يُنشئ التقرير من CSV والـCache محليًا، وتحليل Cloud Run معطّل افتراضيًا. `--cache-path` يحدد ملف الـCache، و`--processing-input` يحدد ملف الدفعة. استخدم `--prepare-only` لتجهيز الدفعة دون استبدال التقرير أو تشغيل Cloud Run.

التشغيل اليدوي القديم باقٍ: `python run.py --input imports/current`. هذا مسار Excel/history القديم؛ استخدم نقطة التشغيل الأسبوعية أعلاه لتقرير Dashboard غير التراكمي.

## GitHub Action

الملف `.github/workflows/meta-ads-weekly.yml` يعمل عند تغيير `imports/current/**/*.csv` على `main` أو عبر `workflow_dispatch` من `main`. القراءة نفسها تقتصر على CSV مباشرة داخل `imports/current`؛ لا تضع CSV في مجلدات فرعية. تستخدم جميع التشغيلات مجموعة concurrency واحدة دون إلغاء التشغيل الجاري.

1. يقرأ CSV ويطبق التحليلات الناجحة المخزنة، ثم يجهز دفعة واحدة للفيديوهات غير المحللة بنجاح.
2. عند وجود دفعة، ينشر `docs/data/processing_input.json` بعملية commit فقط إن تغير، ويبني رابط Raw GitHub مربوطًا بـcommit SHA. لا تُمرّر بيانات اعتماد داخل الرابط؛ يجب أن يستطيع Job قراءة هذا الرابط من المستودع.
3. إذا كانت إعدادات Google جاهزة، يصادق عبر Workload Identity Federation ثم يستدعي Python الأمر `gcloud run jobs execute competitors-report` مرة واحدة مع `--wait` وexecution overrides فقط.
4. يقرأ `meta_ads_processing_results/{run_id}` ويفك `payload_json` سواء كان String JSON أو dict، ويتحقق من `source=meta_ads` و`run_id` و`status=completed` قبل الدمج حسب `ad_id`. يدعم أيضًا العقد القديم ذي الحقول المباشرة.
5. يستبدل `latest.json` ببيانات CSV الحالية ويحفظ الـCache، ثم يعمل commit للملفين عند وجود تغيير فقط. commits الناتجة لا تطابق CSV trigger.

إذا فشل auth أو إعداد gcloud أو تنفيذ Job أو قراءة/التحقق من Firestore، يبقى إنشاء التقرير الحالي مستمرًا. لا يُشغّل Cloud Run إذا لم توجد فيديوهات تحتاج معالجة. أي ملف دفعة باقٍ من تشغيل سابق لا يُستخدم لاتخاذ قرار التشغيل؛ القرار من بيانات CSV والـCache الحالية.

## Dashboard Read-only

الواجهة الحالية داخل `docs/` تبقى للقراءة فقط. لا توجد Upload أو File input أو أي إدخال مستخدم لتعديل البيانات. كل رفع CSV يتم من GitHub فقط، والتشغيل الخارجي لـ Cloud Run من GitHub Actions فقط.

## تحليل الفيديو

إذا كانت إعلانات الفيديو الجديدة غير موجودة في `data/video-analysis-cache.json`, يمكن إرسال دفعة واحدة إلى Cloud Run Job `competitors-report` عبر GitHub Actions. لا يتم إنشاء Job جديد، ولا يتم استخدام أي AI API جديد داخل هذا المستودع.

الـCache ملف تقني متتبّع في Git. حالة `success` تمنع الإرسال وتعيد تطبيق `analysis_status` و`video_analysis` على إعلانات الأسبوع الحالي، وحالة `failed` تسمح بإعادة المحاولة. الإعلانات الغائبة لا تُضاف إلى التقرير لمجرد وجودها في الـCache. غياب التكامل لا يُسجَّل كنجاح وهمي، وفشل فيديو واحد لا يمنع دمج الفيديوهات الناجحة.

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

اضبط `CLOUD_RUN_PROCESSING_ENABLED=true` لتفعيل التكامل، مع `GCP_PROJECT_ID` و`GCP_REGION` وبيانات WIF. لا توجد قيم افتراضية للمشروع أو المنطقة؛ يستخدم Firestore مشروع Cloud Run إن لم يحدد `FIRESTORE_PROJECT_ID`. يرفض الكود أي Job غير `competitors-report`. يحتاج حساب الخدمة صلاحية تنفيذ الـJob مع overrides وقراءة نتائج Firestore، ويحتاج Workflow صلاحية `contents: write` للنشر و`id-token: write` للمصادقة. يجب أن تسمح قواعد الفرع بكتابة GitHub Actions؛ لا يغير هذا المشروع تلك القواعد أو إعدادات GitHub Pages.

لا تُضف مفتاح Service Account JSON. ملفات `gha-creds-*.json` المؤقتة وملفات البيئة مستثناة من Git، وتقتصر عمليات `git add` في Workflow على ملفات النتائج المحددة.

مرجع التنفيذ: [Cloud Run execution overrides](https://docs.cloud.google.com/run/docs/execute/jobs)، و[Google GitHub Actions authentication](https://github.com/google-github-actions/auth).

## Firebase Authentication

واجهة GitHub Pages لا تتغير في منطق Firebase Authentication. قائمة المستخدمين المسموحين تبقى داخل `docs/js/firebase-config.js` ضمن `ALLOWED_EMAILS`, وتُدار كما كان سابقًا.

## الاختبارات

```powershell
python -m unittest discover -s tests -v
```
