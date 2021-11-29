# BOOKING IN BERLINS VACCINATION CENTERS
This python script books automatically a slot on Doctolib in one of the public vaccination centers in Berlin. The source code is based strongly on [doctoshotgun](https://github.com/rbignon/doctoshotgun). It requires python 3.7 or higher.


### Python dependencies

- [woob](https://woob.tech)
- [cloudscraper](https://github.com/venomous/cloudscraper)
- dateutil
- termcolor

### How to use it

Install dependencies:

```
pip install -r requirements.txt
```

Run:

```
python3 booker.py {first,second,booster} <email> [password]
```

You can restrict the search period, by defining the start date with `--start-date <yyyy-mm-dd>` (default value is the current date) and the amount of days after the start date with `--time-window <days>` (by default 14 days).

Excluding certain vaccination centers is possible, e.g. `--exclude-tegel`. All options can be printed using the `-h` flag.

```
usage: booker.py [-h] [--debug] [--dry-run] [--start-date START_DATE] [--time-window TIME_WINDOW] [--exclude-messe] [--exclude-tegel] [--exclude-ring-center] [--exclude-karlshorst] {first,second,booster} username [password]

Book a vaccination slot on Doctolib in Berlin

positional arguments:
  {first,second,booster}
  username              Doctolib username
  password              Doctolib password

optional arguments:
  -h, --help            show this help message and exit
  --debug, -d           show debug information
  --dry-run             do not really book the slot
  --start-date START_DATE
                        Start date of search period (yyyy-mm-dd)
  --time-window TIME_WINDOW
                        Length of the search period in of days after the start date
  --exclude-messe       Exclude center at Messe Berlin
  --exclude-tegel       Exclude center at Flughafen Tegel
  --exclude-ring-center Exclude center at Ring-Center
  --exclude-karlshorst  Exclude center at Trabrennbahn Karlshorst
  ```