
# Fixed list (2024-2-26)
- Lite plan users should see only  venue, and phone, address and website
- Added Mater View mode
- Added URLs list view again for list users
- Change that logic to "x credits remaining"
- Added Copy function in credited data view
- Fix scraping issue for permium/normal users
- Fixed login , signup issue (use only email)
- Fixed the issue that campaign send multi emails at a time. and not working sometimes
- Added new columne to see available credit in admin page
- Added monlty credit column

# Create vapid
npx web-push generate-vapid-keys

TESTING 2024-11-12
// 1. Put REMINDERS tab above UPLOAD CONTACTS tab 
// 2. THIS GOT OVER LOOKED ENTIRELY —> DB should accept individual contacts, and/or contact lists that have ZERO emails listed. 
Currently it just deletes the entire contact. (and db should always include the email in the “bad email” column in our db 
as well as export any lists from our db, and give user bad email column and info). 
2A) Any email that might be uploaded in future, and matches email “bad email” will automatically be accepted by db, 
BUT instantly unsubscribed) This is to avoid uploading or contacting “bad emails” that have already been archived as “bad” ||||| 
*2B) Consider the scenario ….. user emails a venue with only email 1….they respond 
“you’ve contacted the wrong email address, but please message example@example.com; they are the correct person to talk to”….
so user can go into contacts tab, search & find that venue and replace email 1 with the new example@example.com email, 
and move the “wrong email” to the “bad email” column AND if campaign is running with that venue in it….
db/campaign will start contacting that new email since they are subscribed
//3. In regards to #2 - 2B - “EDIT” should include “bad email” field
// 4. Push notification not working on past due or current due reminders (and it should have the remind me in a hour/7 day /complete 
attached to it where clicking either option will push an update to the 
actual reminder…not the push notification). 
Should appear in top right corner of EVERY screen/tab of our UI (yes, It should be annoying on purpose)
// 5. Dont let reminders app create duplicates (the deduplication feature is based on EMAIL ONLY)….if user gets multiple responses from DIFFERENT emails from SAME venue…it’s ok to have 2+ separate reminders in there, which is telling user to review those 2 different emails

// 7. “Remind me in a hour” should be “an hour” from exactly current time (otherwise user gets error) 
// 8. AUTO Reminder that is generated -> time should always be 2pm (of users time zone), and default time for user created reminders & date 7 days from users current date/time (as default but user can edit)
// 9. “How-To & FAQ” Is what the tab should be called…..there should be an option where admin can add a check box that user can interact with …Admin will make a check list of to do items, and user can check and uncheck them..to make sure everything is done before launching their campaign 
// 10. Put “Venue” as first editable field in reminders…user starts to type in and it can auto populate, and user can click it, but theres always a 2nd option called “add new” where user can add a reminder that doesnt have a preexisting contact in upload contacts section SYNC
// 11. Similar to #10 the sync works both ways - in either direction. Meaning in “contacts” page user can click into a “contact card” and under the options there is currently two options EDIT & DELETE…There should be a 3rd called “Create Reminder”, and after it’s clicked it’ll redirect user to the remindrers tab with all the necessary fields filled in base don the “contact card” they clicked and the default time/date (see#7), but user can change SYNC
// 12. SYNC reminders to contacts (where the info updates on both end).., and unsub/delete contact will remove reminder
