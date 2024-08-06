# What is this?
This is an attempt at making the [WuWa DPS Calculator](https://docs.google.com/spreadsheets/d/1vTbG2HfkVxyqvNXF2taikStK-vJJf40QrWa06Fgj17c/edit#gid=0) from [@Maygi](https://github.com/Maygi) run locally using databases in an effort to significantly improve its runtime.

# WIP notice
This is heavily WIP and so far only the creation of the databases works. There is a rough draft for the calculator but it still requires tweaks to be made functional.

# How to make the databases myself?
If you want to create the databases yourself, make sure to put the `credentials.json` file into the `credentials` folder, then run `import_sheets.py` using Python (preferably 3.11).

To get your own credentials.json file, follow [the guide here](https://docs.gspread.org/en/latest/oauth2.html#for-end-users-using-oauth-client-id).

Make sure that you have the requirements installed listed in `requirements.txt`.  
You can install these with `pip install -r requirements.txt` in your terminal.

# License
Due to PyQt5 this project has to be licensed under GPL.
Personally i'll be happy as long as you provide credit.
