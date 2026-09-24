# Meta Ads Weekly Intelligence V1

أداة Python بسيطة لقراءة ملفات CSV المصدرة يدويًا من إضافة FB Ad Library Insights، دمجها، إزالة التكرار حسب `ad_id`، مقارنة كل فحص بالسجل التاريخي، وإنشاء تقرير Excel عربي.

## التثبيت

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## التشغيل

ضع كل ملفات CSV الخاصة بالفحص داخل مجلد واحد، مثل `imports/2026-09-24`، ثم شغّل:

```powershell
python run.py --input imports/2026-09-24
```

يمكن تمرير بيانات اختيارية للتقرير:

```powershell
python run.py --input imports/2026-09-24 --competitor "اسم المنافس" --page-id "123456789"
```

ينتج التقرير في `reports/إعلانات_المنافسين_YYYY-MM-DD.xlsx`، ويُحفظ السجل في `archive/history.json`.

ينتج كل تشغيل ناجح أيضًا بيانات اللوحة في `docs/data/latest.json`. واجهة GitHub Pages تقرأ هذا الملف فقط؛ لا يتم نشر ملفات CSV أو Excel.

## GitHub Pages

لتفعيل الواجهة من GitHub:

`Settings → Pages → Deploy from a branch → main → /docs`

قبل الاستخدام، أضف Google Client ID في `docs/js/auth.js` داخل `GOOGLE_CLIENT_ID`. يمكن تعديل قائمة البريد المسموح مستقبلًا في `ALLOWED_EMAILS` بالملف نفسه. هذا تسجيل دخول كحاجز تجربة استخدام لموقع Static، وليس نظام حماية للبيانات الحساسة، ولا يستخدم Google Client Secret في الواجهة.

للاختبار المحلي فقط، يظهر زر `الدخول التجريبي المحلي` تلقائيًا عند تشغيل الموقع على `localhost` أو `127.0.0.1`. لا يعمل هذا الوضع على GitHub Pages أو أي نطاق آخر، ولا يجب اعتباره حماية أمنية.

## قواعد البيانات والخصوصية

المجلدات `imports/` و`reports/` و`archive/` مستثناة من Git. كما يتم تجاهل ملفات CSV وExcel وقواعد البيانات وملفات `.env`. لا تضع بيانات حساسة في المستودع.

السجل يتتبع `first_seen` و`last_seen` و`times_seen` لكل إعلان. غياب إعلان من عينة لاحقة لا يغيّر السجل ولا يُصنّف الإعلان على أنه متوقف؛ البيانات عينة وليست دليلًا على التوقف.

## الاختبارات

```powershell
python -m unittest discover -s tests -v
```
