"""Records machine: a doctor list's recordings, from the channel to the site's storage (year 1 first).

    py -m spine records plan [--doctor X]          what would be fetched, MB per doctor (from the cached mother maps)
    py -m spine records status [--doctor X]        state of every record, and what is left
    py -m spine records download [--doctor X] [--max-mb N] [--youtube]
    py -m spine records compress [--doctor X]
    py -m spine records upload [--doctor X] [--limit N]
    py -m spine records run [--doctor X] [--max-mb N]   download, compress, upload in one go (a small batch)

See `machine.py` for the states and where every file lives.
"""
