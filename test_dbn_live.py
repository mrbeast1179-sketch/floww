import databento as db
client = db.Live(key="db-PBRQ7ia8dQ8wi6Yj7imWDfxXxGFrN")
client.subscribe(
    dataset="OPRA.PILLAR",
    schema="trades",
    stype_in="parent",
    symbols="SPY.OPT",
)
client.add_callback(print)
client.start()
client.block_for_close(timeout=10)
