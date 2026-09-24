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

## قواعد البيانات والخصوصية

المجلدات `imports/` و`reports/` و`archive/` مستثناة من Git. كما يتم تجاهل ملفات CSV وExcel وقواعد البيانات وملفات `.env`. لا تضع بيانات حساسة في المستودع.

السجل يتتبع `first_seen` و`last_seen` و`times_seen` لكل إعلان. غياب إعلان من عينة لاحقة لا يغيّر السجل ولا يُصنّف الإعلان على أنه متوقف؛ البيانات عينة وليست دليلًا على التوقف.

## الاختبارات

```powershell
python -m unittest discover -s tests -v
```
