# Capital Gains FIFO Desktop App

אפליקציית Windows מקומית לחישוב רווח/הפסד הון מניירות ערך לפי FIFO, על בסיס דוחות אקסל של אגיס ולאומי.

## מה קיים כרגע

- קריאת דוחות Excel וזיהוי אוטומטי של שורת הכותרות.
- ניקוי שורות פתיחה, סיכומים והערות.
- נרמול תנועות מאגיס ולאומי למבנה אחיד.
- חישוב FIFO עם עמלות בתוך עלות קניה/תמורת מכירה.
- טיפול בסיסי באיחודי הון, Reverse Split, הקטנת הון והחלפת נייר.
- תמיכה גם בדוח יחיד של נייר ערך אחד, וגם בכמה דוחות יחד.
- הצגת 5 תובנות מרכזיות אוטומטיות מהדוח שמנותח.
- שליפת שער דולר יציג מבנק ישראל חודש אחורה מתאריך מבוקש.
- יצוא דוח Excel עם גיליונות Dashboard, Summary, Realized FIFO, Open Positions, Transactions, Corporate Actions, Validation Issues.
- GUI ב-CustomTkinter עם בחירת קבצים, Drag & Drop כאשר `tkinterdnd2` מותקן, וייצוא בלחיצה.
- CLI לאימות חישוב בלי ממשק.

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
