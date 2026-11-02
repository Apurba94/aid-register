# Aid Register

An offline register for distributions of food or relief items, for places with no reliable internet. It calculates what each household should get, stops double collection, and suggests possible duplicate records for a person to review.

```
python -m aid_register
```

Then open http://127.0.0.1:8031. It needs Python 3.10 or newer, and nothing else.

## What it does

- **Register households** and search by name, number or phone
- **Distribution rounds** with a ration scaled by household size, with caps, for example `Rice kg, 0, 6, 40`
- **Stock totals** to order before the day, and what has been given so far
- **Double collection is blocked** by the database itself, not only by the screen, and a warning tells staff to call a supervisor
- **A list of who has not collected,** so that outreach can reach them
- **Duplicate suggestions** that use fuzzy name matching, phone, father's name and age

## Duplicates: a person always decides

Transliterated names vary: Rahima Khatun and Rohima Khatoon may be one person, and many different people share a name. The app only suggests pairs, with its reasons. Nothing is merged or removed until a person decides, ideally after talking to those concerned. Wrongly removing a family can mean they go hungry, so false alarms matter as much as missed duplicates.

## Data protection: please read first

This app stores personal data about people who may be at serious risk. **Do not put real data in it until your organisation's data protection lead has reviewed it.** In particular:

- The data file is **not encrypted**. Use full-disk encryption, and keep the file off shared and removable drives.
- There are **no user accounts or logins.** Anyone at the computer can read everything.
- Collect only what you need, and agree how long to keep it.
- Never share lists of names, or send them over open channels.

This is an independent open-source project. It is not a product of, or endorsed by, any humanitarian organisation, and it does not replace tools such as those approved by your agency.

## How it is tested

The string measures reproduce published Jaro and Jaro-Winkler values. Name tests cover real transliteration patterns and pairs that must stay apart. Blocking is compared with a full comparison, and a 5,000-record register must finish quickly. App tests confirm that a second collection is refused and that no one is removed without a decision.

Matching was tuned on made-up examples, and has not been measured on a real register. Check its suggestions before relying on them.

## Limits

One computer at a time, with no sync between sites. There is no ID card printing, barcode or biometric support. Name rules are aimed at South Asian English transliteration.

## Tests

```
python -m unittest discover -s tests
```

MIT licence.
