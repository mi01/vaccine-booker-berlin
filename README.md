# BOOKING IN BERLINS VACCINATION CENTERS
This python script books automatically a slot on Doctolib in one of the public vaccination centers in Berlin. The source code is based strongly on [doctoshotgun](https://github.com/rbignon/doctoshotgun).


### Python dependencies

- [woob](https://woob.tech)
- cloudscraper
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

By default AstraZeneca vaccine is excluded. You can include it with `--astrazeneca` or `-az`.
