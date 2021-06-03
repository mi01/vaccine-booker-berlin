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

By default AstraZeneca vaccine is excluded. You can include it with `--astrazeneca` or `-az`. You can also restrict the search period, by defining the start date with `--start-date <yyyy-mm-dd>` (default value is the current date) and the amount of days after the start date with `--period-length <days>` (by default 14 days).
