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
python3 booker.py <email> [password]
```

By default AstraZeneca vaccine is excluded. You can include it with `--astrazeneca` or `-az`. You can also restrict the search period, by defining the start date with `--start-date <yyyy-mm-dd>` (default value is the current date) and the amount of days after the start date with `--time-window <days>` (by default 14 days).

Excluding certain vaccination centers is possible, e.g. `--exclude-tempelhof`. All options can be printed using the `-h` flag.

```
usage: booker.py [-h] [--debug] [--start-date START_DATE] [--time-window TIME_WINDOW] [--astrazeneca] [--exclude-arena] [--exclude-tempelhof] [--exclude-messe] [--exclude-velodrom] [--exclude-tegel] [--exclude-eisstadion] username [password]

Book a vaccination slot on Doctolib in Berlin

positional arguments:
  username                      Doctolib username
  password                      Doctolib password

optional arguments:
  -h, --help                    show this help message and exit
  --debug, -d                   show debug information
  --start-date <yyyy-mm-dd>     Start date of search period (yyyy-mm-dd)
  --time-window <days>          Length of the search period in of days after the start date
  --astrazeneca, -az            Include AstraZeneca vaccine
  --exclude-arena               Exclude center at Arena Berlin
  --exclude-tempelhof           Exclude center at Flughafen Tempelhof
  --exclude-messe               Exclude center at Messe Berlin
  --exclude-velodrom            Exclude center at Velodrom Berlin
  --exclude-tegel               Exclude center at Flughafen Tegel
  --exclude-eisstadion          Exclude center at Erika-Heß-Eisstadion
  ```