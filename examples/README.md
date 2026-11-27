# Examples

`query_visits_sample.json` is a **synthetic** BeenEverywhere `/query-visits`
response with placeholder coordinates. It is only there to demonstrate the
file shape; it is not tied to any real person's map.

Parse it without contacting BeenEverywhere:

```bash
been2guessr inspect --input examples/query_visits_sample.json
```

To build a real map, save your own public map's response:

```bash
curl https://beeneverywhere.net/query-visits/<username> -o my-places.json
been2guessr build --input my-places.json -n 300 -o my-map.json --csv
```

Or skip the file entirely and pass the username/URL directly.
