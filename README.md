# Capital Gains FIFO Desktop App

אפליקציית Windows מקומית לחישוב רווח/הפסד הון מניירות ערך לפי FIFO, על בסיס דוחות אקסל של אגיס ולאומי.

## מה קיים כרגע

- קריאת דוחות Excel וזיהוי אוטומטי של שורת הכותרות.
- זיהוי דוחות גם לפי aliases של כותרות עמודות, לא רק לפי שני סטים קשיחים.
- זיהוי גנרי של דוחות חדשים לפי headers נפוצים, גם כשהמבנה לא זהה לאגיס/לאומי.
- שמירת תבניות התאמת עמודות מקומיות, כדי ללמד את האפליקציה דוח חדש פעם אחת בלבד.
- ניקוי שורות פתיחה, סיכומים והערות.
- נרמול תנועות מאגיס ולאומי למבנה אחיד.
- חישוב FIFO עם עמלות בתוך עלות קניה/תמורת מכירה.
- טיפול בסיסי באיחודי הון, Reverse Split, הקטנת הון והחלפת נייר.
- תמיכה גם בדוח יחיד של נייר ערך אחד, וגם בכמה דוחות יחד.
- הצגת 5 תובנות מרכזיות אוטומטיות מהדוח שמנותח.
- שליפת שער דולר יציג מבנק ישראל חודש אחורה מתאריך מבוקש.
- יצוא דוח Excel עם גיליונות Dashboard, Summary, Realized FIFO, Open Positions, Transactions, Corporate Actions, Validation Issues.
- GUI ב-CustomTkinter עם בחירת קבצים, Drag & Drop כאשר `tkinterdnd2` מותקן, וייצוא בלחיצה.
- אזור `שאלי את הדוח` שמספק תשובות מקומיות מתוך הנתונים שנותחו, כולל שאלות על נייר מסוים, טווח תאריכים, השוואה בין ניירות וחריגות.
- CLI לאימות חישוב בלי ממשק.
- שכבת Google Sign-In מקומית ל-Desktop: התחברות דרך הדפדפן, שמירת session מקומית, וברכה שנגזרת מהאימייל של המשתמש.
- שכבות שירות נפרדות לניתוח, Q&A, תבניות דוחות ו-auth, כהכנה להפרדת ליבת הניתוח מהממשק.
- שכבת `application workflow` שמרכזת state ו-use cases, כדי לאפשר בעתיד ממשקי Windows/Android מעל אותה לוגיקה.

## התקנה מקומית

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

אם `py` לא זמין במחשב, יש להתקין Python 3.12+ ל-Windows ולסמן בהתקנה `Add python.exe to PATH`.

## הרצת GUI

```powershell
.\.venv\Scripts\python.exe app.py
```

לבדיקת ברכה דינמית לפני חיבור Google Sign-In מלא:

```powershell
$env:CAPITAL_GAINS_USER_EMAIL="liat.cohen@gmail.com"
.\.venv\Scripts\python.exe app.py
```

בעת חיבור Google Sign-In, שם התצוגה באפליקציה ייגזר מהאימייל של המשתמש.

## Google Sign-In ל-Desktop

1. צרי ב-Google Cloud OAuth Client מסוג `Desktop app`.
2. שמרי את קובץ ה-JSON בשם `google_client_secret.json`.
3. הניחי אותו באחד מהמיקומים הבאים:

```text
config\google_client_secret.json
%LOCALAPPDATA%\CapitalGains\google_client_secret.json
```

אפשר גם להגדיר נתיב מותאם דרך משתנה הסביבה:

```powershell
$env:CAPITAL_GAINS_GOOGLE_CLIENT_SECRET="C:\path\to\google_client_secret.json"
```

האפליקציה שומרת את ה-session מקומית על המחשב ואינה מעלה את דוחות האקסל לענן.

## התאמת עמודות לדוח חדש

כאשר נטען דוח חדש שהמערכת לא מזהה במלואו, אפשר להשתמש בכפתור `התאמת עמודות` בממשק:

1. בוחרים את שורת הכותרות שזוהתה.
2. ממפים תאריך, פעולה, כמות, מזהה נייר ומחיר/תמורה.
3. שומרים תבנית מקומית.

התבנית נשמרת ב-`%LOCALAPPDATA%\CapitalGains\report_templates.json` ותשמש גם בהרצות הבאות.

## כיווני פיתוח קרובים

- הפרדת ליבת הניתוח מהממשק כדי לאפשר Microsoft Store ו-Android בהמשך.
- הרחבת מנוע השאלות המקומי כך שיכלול הסברים עמוקים יותר, השוואות בין ניירות ותמיכה בסינונים.
- חיבור מאובטח של זהות משתמש גם למסלולי Android ו-Windows Store.
- הרחבת מנוע השאלות המקומי לשפה חופשית יותר, כולל שאלות מורכבות יותר על מס, מטבע ואירועי הון.

## כיוון Multi-Platform

הקוד כבר מתחיל להיות מחולק כך:

- `capital_gains_app/application.py` מנהל state ופעולות אפליקטיביות.
- `capital_gains_app/gui.py` נשאר שכבת תצוגה ל-Desktop.
- `capital_gains_app/parsers.py`, `fifo.py`, `exporter.py`, `qa.py` נשארים לוגיקה משותפת.

במילים פשוטות: כדי להגיע בהמשך ל-Windows Store או Android, נוכל להחליף את שכבת ה-UI בלי לכתוב מחדש את מנוע הניתוח.

## הרצת Console / Alpha

```powershell
.\.venv\Scripts\python.exe -m capital_gains_app.cli "דוח תנועות בנק אגיס.xlsx" "תנועות בניירות ערך בלל.xlsx" --output outputs\fifo_report.xlsx
```

אפשר להריץ גם על קובץ יחיד:

```powershell
.\.venv\Scripts\python.exe -m capital_gains_app.cli "single-security-report.xlsx" --output outputs\single_security_fifo.xlsx --exchange-date 2026-06-29
```

## בניית EXE

```powershell
.\build_exe.ps1
```

הקובץ ייווצר תחת:

```text
dist\CapitalGainsFIFO.exe
```

## הערות מקצועיות

הדוחות לדוגמה כוללים מכירות בתחילת התקופה ללא קניות קודמות באותו קובץ. במקרים כאלה המערכת מסמנת חוסר מלאי. כאשר קיים בדוח לאומי רווח/הפסד מדווח של הבנק, המערכת יכולה להסיק עלות היסטורית חסרה כדי שהדוח לא ייעצר, אך היא מסמנת זאת בשדה `inferred`.

המערכת אינה תחליף לייעוץ מס. לפני שימוש מול לקוחה אמיתית צריך לאמת מדגם עסקאות ידנית מול דוחות מקוריים ואישורי בנק.
