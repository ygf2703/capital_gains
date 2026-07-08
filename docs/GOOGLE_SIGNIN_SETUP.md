# הגדרת Google Sign-In עבור Capital Gains

מסמך זה מיועד למי שמגדיר את האפליקציה, אורז אותה, או מתקין אותה לראשונה בסביבת עבודה.

המטרה שלו פשוטה: להפעיל התחברות עם Google עבור גרסת ה-Desktop של Capital Gains, בצורה שתואמת גם את התיעוד הרשמי של Google וגם את מה שהאפליקציה מצפה לו בפועל.

## מה האפליקציה צריכה

כדי ש-Google Sign-In יעבוד בגרסת ה-Desktop, האפליקציה צריכה קובץ OAuth Client מסוג:

`Desktop app`

הקובץ צריך להיות קובץ JSON שמכיל credentials תקינים, והאפליקציה מחפשת אותו באחד מהמיקומים הבאים:

```text
config\google_client_secret.json
%LOCALAPPDATA%\CapitalGains\google_client_secret.json
```

אפשר גם להגדיר נתיב חיצוני דרך משתנה הסביבה:

```powershell
$env:CAPITAL_GAINS_GOOGLE_CLIENT_SECRET="C:\path\to\google_client_secret.json"
```

## מה האפליקציה עושה בפועל

בקוד הנוכחי, Google Sign-In משמש עבור:

- זיהוי משתמש
- קבלת אימייל
- קבלת שם תצוגה
- ניהול session מקומי

ה-flow מבוסס על:

- OAuth ל־Desktop app
- פתיחת דפדפן מערכת
- `openid`
- `email`
- `profile`

אחרי ההתחברות:

- נשמר token מקומי
- נשמר profile מקומי
- שם התצוגה נגזר מהאימייל, עם fallback לשם שמוחזר מ-Google

## שלב 1: יצירת Project ב-Google Cloud

1. היכנס ל-[Google Cloud Console](https://console.cloud.google.com/)
2. צור Project חדש או בחר Project קיים
3. ודא שאתה עובד בתוך ה-Project הנכון

## שלב 2: הגדרת OAuth consent screen

לפי התיעוד הרשמי של Google, קודם צריך להגדיר את מסך ההסכמה של OAuth.

בממשק הנוכחי של Google זה נמצא תחת:

`Google Auth platform > Branding`

מקור רשמי:
- [Configure the OAuth consent screen](https://developers.google.com/workspace/guides/configure-oauth-consent)

מה למלא:

1. `App name`  
   לדוגמה: `Capital Gains`

2. `User support email`  
   אימייל תמיכה פעיל

3. `Audience / User type`  
   לרוב: `External`

4. `Developer contact information`  
   אימייל איש קשר

### הערה חשובה

אם האפליקציה עדיין לא פורסמה רשמית או לא עברה verification, מומלץ להוסיף את המשתמשים הנדרשים כ־`Test users`.

## שלב 3: יצירת OAuth Client ל-Desktop

לפי התיעוד הרשמי של Google, עבור אפליקציית Windows מקומית יש ליצור client מסוג `Desktop app`.

בממשק הנוכחי זה נמצא תחת:

`Google Auth platform > Clients`

מקור רשמי:
- [Create access credentials](https://developers.google.com/workspace/guides/create-credentials)
- [OAuth 2.0 for iOS & Desktop Apps](https://developers.google.com/identity/protocols/oauth2/native-app)

השלבים:

1. היכנס לעמוד `Clients`
2. לחץ על `Create Client`
3. בחר `Application type > Desktop app`
4. תן שם ל-client  
   לדוגמה: `Capital Gains Desktop`
5. לחץ על `Create`

לאחר מכן הורד את קובץ ה-JSON.

## שלב 4: שמירת הקובץ במיקום הנכון

שמור את הקובץ בשם:

```text
google_client_secret.json
```

והנח אותו באחד מהמיקומים הבאים:

### אפשרות מומלצת למפתחים / Build

```text
config\google_client_secret.json
```

### אפשרות מומלצת להתקנה מקומית אצל משתמש

```text
%LOCALAPPDATA%\CapitalGains\google_client_secret.json
```

### אפשרות מותאמת

הגדרת נתיב חיצוני דרך משתנה סביבה:

```powershell
$env:CAPITAL_GAINS_GOOGLE_CLIENT_SECRET="C:\path\to\google_client_secret.json"
```

## שלב 5: מה האפליקציה בודקת בקובץ

האפליקציה בודקת שהקובץ:

- קיים
- הוא JSON תקין
- מכיל בלוק `installed` או `web`
- מכיל את השדות החיוניים:
  - `client_id`
  - `client_secret`
  - `auth_uri`
  - `token_uri`

אם הקובץ לא תקין, האפליקציה תציג שגיאה ברורה במסך Google setup.

## שלב 6: בדיקה מתוך האפליקציה

אחרי ששמרת את הקובץ:

1. פתח את האפליקציה
2. עבור למסך ההתחברות
3. לחץ על:
   - `כניסה עם Google`
   - או `הגדר התחברות עם Google`
4. אם הכל הוגדר נכון:
   - ייפתח דפדפן מערכת
   - תתבצע כניסה
   - עם החזרה לאפליקציה המשתמש ייחשב כמחובר

## מה נשמר מקומית

האפליקציה שומרת מידע מקומי בנתיבים דומים לאלה:

```text
%LOCALAPPDATA%\CapitalGains\profile.json
%LOCALAPPDATA%\CapitalGains\google_token.json
```

בנוסף, אם משתמשים בחשבון מקומי:

```text
%LOCALAPPDATA%\CapitalGains\users.json
```

## תקלות נפוצות

### 1. הכפתור של Google מופיע, אבל החיבור לא מתחיל

מה לבדוק:

- האם קובץ ה-JSON נמצא במיקום הנכון
- האם שם הקובץ נכון
- האם הקובץ תקין ולא נפגם

### 2. מתקבלת שגיאה על missing fields

זה אומר שהקובץ שהוזן אינו קובץ OAuth Client מתאים, או שאינו קובץ מלא.

מה לעשות:

- להוריד מחדש את קובץ ה-JSON מתוך `Google Auth platform > Clients`
- לוודא שנבחר client מסוג `Desktop app`

### 3. הדפדפן נפתח אבל Google לא מאשר את הכניסה

מה לבדוק:

- האם המשתמש נוסף כ־`Test user`
- האם OAuth consent screen הוגדר
- האם עובדים על ה-Project הנכון

### 4. יש התחברות, אבל המשתמש לא נשמר

מה לבדוק:

- האם לאפליקציה יש הרשאות כתיבה לתיקיית `%LOCALAPPDATA%\CapitalGains`
- האם תוכנת אבטחה חוסמת כתיבת token/profile

## מה לא לעשות

- לא ליצור client מסוג `Web application` עבור גרסת ה-Desktop
- לא לשתף את קובץ ה-client secret במקומות ציבוריים
- לא להניח שאותו client ישמש גם Android

## הערה לגבי Android

כאשר נגיע לגרסת Android, נצטרך ליצור OAuth Client נפרד מסוג:

`Android`

עם package name ו־SHA-1 תואמים.

ה-client של Desktop לא אמור לשמש כאחד לאחד גם באנדרואיד.

## מקורות רשמיים

- [Configure the OAuth consent screen](https://developers.google.com/workspace/guides/configure-oauth-consent)
- [Create access credentials](https://developers.google.com/workspace/guides/create-credentials)
- [OAuth 2.0 for iOS & Desktop Apps](https://developers.google.com/identity/protocols/oauth2/native-app)
- [Using OAuth 2.0 to Access Google APIs](https://developers.google.com/identity/protocols/oauth2)

## התאמה לקוד הקיים

המסמך הזה תואם למה שהאפליקציה בודקת בפועל בקבצים:

- [capital_gains_app/auth.py](../capital_gains_app/auth.py)
- [capital_gains_app/gui.py](../capital_gains_app/gui.py)

בפרט:

- איתור קובץ ההגדרה
- בדיקת תקינותו
- פתיחת flow בדפדפן
- שמירת token ו-session מקומיים
