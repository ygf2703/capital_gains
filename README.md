# Capital Gains

אפליקציית Desktop מקומית ל-Windows לניתוח דוחות ניירות ערך, חישוב רווח/הפסד הון לפי FIFO, הפקת דוח Excel מסכם, והצגת דשבורד ותובנות מתוך הנתונים.

האפליקציה בנויה כך שהלוגיקה העסקית נשארת מקומית על המחשב, בלי תלות בענן לצורך ניתוח הדוחות עצמם. במקביל, המבנה הפנימי כבר הוכן להמשך הדרך אל Microsoft Store ואל Android.

## מה האפליקציה יודעת לעשות היום

- טעינת דוחות Excel של בנקים וברוקרים, כולל תמיכה בדוחות מוכרים ובדוחות גנריים לפי headers.
- זיהוי אוטומטי של שורת הכותרות, ניקוי שורות פתיחה, סיכומים והערות.
- שמירת תבניות מיפוי עמודות מקומיות, כך שאפשר "ללמד" את המערכת דוח חדש פעם אחת.
- חישוב FIFO מלא לקניות ומכירות.
- טיפול באירועי הון כמו `split`, `reverse split`, `capital reduction` והחלפות נייר.
- תמיכה גם בדוח יחיד של נייר אחד וגם בכמה קבצים יחד.
- משיכת שער דולר מבנק ישראל חודש אחורה מתאריך מבוקש, ושמירתו כחלק מהחישוב.
- הפקת קובץ Excel מסכם עם גיליונות של dashboard, שורות FIFO, פוזיציות פתוחות, תנועות, אירועי הון והתראות.
- דשבורד גרפי עם KPI, תובנות מרכזיות וגרפים.
- ממשק RTL מלא ב־`CustomTkinter`, עם Drag & Drop כאשר `tkinterdnd2` מותקן.
- מסך התחברות עם שני מסלולים:
  - משתמש מקומי עם אימייל וסיסמה
  - התחברות עם Google
- מסך `Account / Settings` לניהול סטטוס התחברות וחיבור Google.
- צ'אט פנימי לניתוח הדוח:
  - מענה על שאלות על רווחים, תנועות, פוזיציות פתוחות, חריגות, אירועי הון ושער דולר
  - החזרת אסמכתאות מתוך הדוח עצמו
  - שאלות המשך חכמות לפי ההקשר של השאלה האחרונה

## עקרונות מוצר

- דוח הברוקר הוא מקור האמת לחישוב ה-FIFO.
- מקורות שוק חיצוניים, אם נחבר בהמשך, ישמשו להעשרה, ולידציה והשלמות, לא לדריסת נתוני העסקאות.
- כל הניתוחים נשמרים מקומית.
- המערכת בנויה לשימוש פרקטי, עם הסבריות מספקת למשתמש ולא רק "מנוע חישוב שחור".

## ארכיטקטורה בקצרה

- [capital_gains_app/application.py](./capital_gains_app/application.py)  
  שכבת workflow וניהול state אפליקטיבי.

- [capital_gains_app/gui.py](./capital_gains_app/gui.py)  
  שכבת ה-UI של אפליקציית ה-Desktop.

- [capital_gains_app/parsers.py](./capital_gains_app/parsers.py)  
  קריאת קבצים, זיהוי headers ונרמול דוחות.

- [capital_gains_app/fifo.py](./capital_gains_app/fifo.py)  
  מנוע FIFO וחישובי מלאי/מימוש.

- [capital_gains_app/dashboard.py](./capital_gains_app/dashboard.py)  
  בניית תקציר dashboard ותובנות.

- [capital_gains_app/qa.py](./capital_gains_app/qa.py)  
  מנוע Q&A, אסמכתאות מהדוח, ושאלות המשך חכמות.

- [capital_gains_app/exporter.py](./capital_gains_app/exporter.py)  
  יצוא דוח Excel סופי.

- [capital_gains_app/auth.py](./capital_gains_app/auth.py)  
  התחברות מקומית, Google Sign-In וניהול session.

המבנה הזה מאפשר להחליף בהמשך את שכבת ה-UI בלי לכתוב מחדש את ליבת הניתוח.

## דרישות מערכת

- Windows
- Python 3.12+
- Excel reports בפורמט `xlsx` / `xlsm` / `xls`

## התקנה מקומית

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

אם `py` לא זמין:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## הרצת האפליקציה

```powershell
.\.venv\Scripts\python.exe app.py
```

## הרצת בדיקות

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

## מסמכי עזר

- [מדריך עבודה למשתמש](./docs/USER_GUIDE_HE.md)
- [הגדרת Google Sign-In](./docs/GOOGLE_SIGNIN_SETUP.md)
- [מסמכי docs נוספים](./docs/README.md)

## הרצת CLI

לשימוש אלפא או לאימות חישוב בלי ממשק:

```powershell
.\.venv\Scripts\python.exe -m capital_gains_app.cli "דוח1.xlsx" "דוח2.xlsx" --output outputs\fifo_report.xlsx
```

אפשר גם על קובץ יחיד:

```powershell
.\.venv\Scripts\python.exe -m capital_gains_app.cli "single-security-report.xlsx" --output outputs\single_security_fifo.xlsx --exchange-date 2026-06-29
```

## בניית EXE

```powershell
.\build_exe.ps1
```

הפלט ייווצר תחת:

```text
dist\CapitalGainsFIFO.exe
```

## התחברות והרשמה

עם פתיחת האפליקציה מופיע מסך התחברות. כרגע יש שני מסלולים:

1. אימייל + סיסמה
2. Google Sign-In

המשתמשים המקומיים נשמרים ב:

```text
%LOCALAPPDATA%\CapitalGains\users.json
```

ה-session הפעיל נשמר ב:

```text
%LOCALAPPDATA%\CapitalGains\profile.json
```

## Google Sign-In

האפליקציה כבר כוללת את ה-flow של Google ל־Desktop App. כדי להפעיל אותו צריך רק לספק קובץ OAuth JSON תקין.

### מה צריך להגדיר ב-Google Cloud

1. ליצור או לבחור Project
2. להגדיר OAuth consent screen
3. ליצור OAuth Client מסוג `Desktop app`
4. להוריד את קובץ ה-JSON

### איפה לשים את הקובץ

שמור את הקובץ בשם:

```text
google_client_secret.json
```

באחד מהמיקומים הבאים:

```text
config\google_client_secret.json
%LOCALAPPDATA%\CapitalGains\google_client_secret.json
```

או דרך משתנה סביבה:

```powershell
$env:CAPITAL_GAINS_GOOGLE_CLIENT_SECRET="C:\path\to\google_client_secret.json"
```

### הערות חשובות

- האפליקציה פותחת דפדפן מערכת לצורך ההתחברות.
- שם התצוגה של המשתמש נגזר מהאימייל, עם fallback לשם ש-Google מחזיר.
- לא מעלים את דוחות האקסל לענן במסגרת תהליך ההתחברות.

## עבודה עם דוח חדש שלא מזוהה אוטומטית

אם הועלה דוח חדש והמערכת לא מזהה את כל השדות הדרושים:

1. לבחור קובץ
2. ללחוץ על `התאמת עמודות`
3. למפות את השדות הנדרשים
4. לשמור תבנית

התבניות נשמרות מקומית ב:

```text
%LOCALAPPDATA%\CapitalGains\report_templates.json
```

## הצ'אט הפנימי

אזור הצ'אט באפליקציה נועד לנתח את הדוח שכבר חושב, ולא להחליף את מנוע ה-FIFO.

הוא יודע כרגע לענות על שאלות כמו:

- מה הרווח הכולל
- מה מצב נייר מסוים
- כמה תנועות היו בטווח תאריכים
- אילו פוזיציות נשארו פתוחות
- אילו חריגות קיימות
- האם היו אירועי הון
- איזה שער דולר שימש
- מה עוד לא מוצג במסך הראשי

בנוסף:

- לכל תשובה אפשר להחזיר אסמכתאות מתוך הדוח
- לאחר תשובה מוצגות שאלות המשך חכמות לפי ההקשר

## מקורות מידע חיצוניים

נכון לעכשיו:

- שער דולר נמשך מבנק ישראל
- נתוני השוק עצמם אינם נמשכים מ-API של בורסה חיצונית כחלק ממנוע המס

הגישה המוצרית כאן מכוונת:

- **דוחות המקור** קובעים את החישוב
- **API חיצוני** יכול בעתיד לעזור ב:
  - מיפוי ניירות
  - אירועי הון
  - ולידציה
  - מידע משלים לדשבורד

כלומר, חיבור עתידי ל-TASE או מקור שוק אחר הוא שכבת enrichment, לא תחליף לדוח הברוקר.

## מבנה תיקיות

```text
assets/                 קבצי עיצוב ומדיה
capital_gains_app/      קוד המקור של האפליקציה
config/                 קובצי הגדרה כמו Google client secret
dist/                   פלט EXE
docs/                   מסמכי עזר
outputs/                דוחות Excel שיוצאו
tests/                  בדיקות אוטומטיות
app.py                  entry point
build_exe.ps1           סקריפט בנייה ל-EXE
CapitalGainsFIFO.spec   קובץ PyInstaller
package_release.ps1     סקריפט אריזה להפצה
```

## Roadmap קרוב

- חידוד נוסף של חוויית החשבון וההגדרות
- חיבור מלא ומלוטש של Google Sign-In להפצה
- שכבת Integrations מסודרת ל-Google, Bank of Israel ומקורות שוק עתידיים
- הרחבת ה-Q&A לשאלות מורכבות יותר על מס, מטבע ואירועי הון
- הכנת שכבת התאמה להמשך הדרך ל-Microsoft Store ול-Android

## דיסקליימר מקצועי

האפליקציה נועדה לסייע בניתוח, ארגון והפקת דוחות, אבל אינה תחליף לייעוץ מס או לייעוץ משפטי.

לפני שימוש מול לקוח אמיתי או דיווח מס בפועל, מומלץ:

- לבדוק מדגם עסקאות מול דוחות המקור
- לאמת אירועי הון חריגים
- לעבור על שורות שסומנו כחריגות או כ־`inferred`

## סטטוס פרויקט

הפרויקט פעיל ונמצא בתהליך שדרוג מתמשך, עם דגש על:

- דיוק חישובי
- UX בעברית ו-RTL
- חוויית משתמש פרימיום ונקייה
- מוכנות הדרגתית למוצר רב-פלטפורמי
