# בניית MSIX עבור Microsoft Store

המסמך הזה מיועד לשלב שבו עוברים מ־`EXE` רגיל לחבילת `MSIX` שאותה נוכל להעלות ל־Microsoft Store.

המטרה כאן היא לא רק "לייצר קובץ", אלא לבנות חבילה שתואמת את זהות האפליקציה ב־Partner Center ותהיה בסיס נכון להגשה לחנות.

## מה נוסף בפרויקט

כדי לתמוך במסלול MSIX נוספו בפרויקט:

- [build_msix.ps1](../build_msix.ps1)  
  סקריפט build ל־MSIX

- [msix/AppxManifest.template.xml](../msix/AppxManifest.template.xml)  
  תבנית manifest לחבילת MSIX

- [config/msix.settings.example.json](../config/msix.settings.example.json)  
  קובץ example להגדרות packaging

## תנאים מוקדמים

לפני הבנייה צריך:

1. Python תקין
2. build תקין של `EXE`
3. Windows SDK מותקן
4. זהות אפליקציה מ־Partner Center

ה־SDK צריך לספק לפחות:

- `makeappx.exe`
- `signtool.exe` אם רוצים חתימה מקומית

## שלב 1: יצירת זהות אפליקציה ב־Partner Center

לפני שממלאים את קובץ ההגדרות, צריך לפתוח אפליקציה ב־Microsoft Partner Center ולשריין שם לאפליקציה.

משם נקבל את הנתונים שצריך למלא ב־MSIX:

- `identityName`
- `publisher`
- `publisherDisplayName`

בלי הערכים האלה אפשר לבנות רק שלד מקומי, אבל לא חבילה מסודרת להגשה לחנות.

## שלב 2: יצירת קובץ הגדרות מקומי

מעתיקים:

```text
config\msix.settings.example.json
```

אל:

```text
config\msix.settings.json
```

וממלאים את השדות:

- `identityName`
- `publisher`
- `publisherDisplayName`
- `displayName`
- `shortDisplayName`
- `description`

דוגמה:

```json
{
  "identityName": "12345YourCompany.CapitalGains",
  "publisher": "CN=ABCD1234-....",
  "publisherDisplayName": "Your Company Name",
  "displayName": "Capital Gains",
  "shortDisplayName": "Capital Gains",
  "description": "Capital gains FIFO desktop analyzer",
  "language": "he-IL",
  "minVersion": "10.0.17763.0",
  "maxVersionTested": "10.0.26100.0",
  "signing": {
    "enabled": false,
    "certificatePath": "",
    "certificatePassword": ""
  }
}
```

## שלב 3: בניית EXE

סקריפט ה־MSIX מריץ כברירת מחדל גם את בניית ה־EXE, ולכן אין חובה לעשות את זה ידנית לפני כן.

אבל אם רוצים:

```powershell
.\build_exe.ps1
```

## שלב 4: בניית MSIX

הפקודה הרגילה:

```powershell
.\build_msix.ps1
```

מה הסקריפט עושה:

1. קורא את גרסת האפליקציה מתוך `capital_gains_app\__init__.py`
2. קורא את `config\msix.settings.json`
3. מאתר את `makeappx.exe`
4. בונה `EXE` אם לא דילגת על השלב
5. יוצר תיקיית staging
6. מייצר `AppxManifest.xml` מתוך template
7. אורז קובץ `MSIX`

הפלט ייווצר תחת:

```text
release\msix\
```

## אפשרויות שימוש

### דילוג על בניית EXE

אם כבר בנית EXE קודם:

```powershell
.\build_msix.ps1 -SkipExeBuild
```

### דילוג על חתימה

אם ההגדרות כוללות חתימה אבל כרגע רוצים רק build:

```powershell
.\build_msix.ps1 -SkipSigning
```

## חתימה

הסקריפט תומך גם בחתימה מקומית, אם ממלאים:

- `signing.enabled = true`
- `certificatePath`
- `certificatePassword`

אם החתימה לא מופעלת, הסקריפט יבנה MSIX לא חתום ויציין זאת במפורש.

## מה נמצא כרגע ב־manifest

ה־manifest מוגדר כרגע עבור:

- `Windows.Desktop`
- אפליקציית `FullTrust`
- הרצת `CapitalGainsFIFO.exe`

ה־logos כרגע מפנים ל:

```text
assets\images\capital_gains_logo.png
```

זה מספיק לשלד build, אבל לפני הגשה אמיתית לחנות כדאי להכין assets ייעודיים במידות המתאימות ל־MSIX.

## מה עוד צריך לפני העלאה לחנות

MSIX build הוא רק חלק אחד מהתהליך.

עדיין צריך:

- Privacy Policy URL אמיתי
- Support URL
- Store listing
- screenshots
- תיאור מוצר סופי
- בדיקות release מלאות

מומלץ לעבור גם על:

- [צ'קליסט שחרור להפצה](./RELEASE_CHECKLIST_HE.md)

## תקלות נפוצות

### 1. Missing msix settings

אם מתקבלת שגיאה על קובץ חסר:

- ליצור `config\msix.settings.json`
- להעתיק מה־example
- למלא ערכים אמיתיים

### 2. Placeholder values

אם יש שגיאה על `REPLACE_...`, המשמעות היא שנשארו ערכי placeholder ולא מולאו ערכי Partner Center אמיתיים.

### 3. makeappx.exe לא נמצא

צריך להתקין Windows SDK.

הסקריפט יודע לחפש:

- ב־`PATH`
- בתיקיות `Windows Kits\10\bin`

### 4. signtool.exe לא נמצא

אותו פתרון: להתקין Windows SDK, או לדלג כרגע על חתימה.

## הערה חשובה על זהות החבילה

כדי להעלות ל־Microsoft Store, הזהות של ה־MSIX צריכה להתאים לזהות שהוקצתה לאפליקציה ב־Partner Center.

אם יש mismatch ב:

- `identityName`
- `publisher`

החבילה לא תהיה מתאימה למסלול Store submission.
