import argparse
import asyncio
from pathlib import Path

from data_fetching import msp_open_data
from databases import init_db, msp_registry


async def main(args: argparse.Namespace) -> None:
    if args.make_slice:
        found = await asyncio.to_thread(msp_open_data.make_slice, Path(args.zip), args.inn, msp_open_data.SLICE)
        print(f"slice: {len(found)} of {len(args.inn)} INNs written to {msp_open_data.SLICE}")
        return
    await init_db()
    if args.zip:
        load = await msp_registry.load(msp_open_data.read_zip(Path(args.zip)), "full", args.zip)
    elif args.full:
        load = await msp_registry.refresh_full()
    else:
        load = await msp_registry.load(msp_open_data.read_slice(), "slice", msp_open_data.SLICE.name)
    print(f"{load.kind}: {load.records} records, registry state on {load.data_date}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Реестр МСП из открытых данных ФНС")
    parser.add_argument("--full", action="store_true", help="скачать свежий полный набор по паспорту meta.csv и загрузить")
    parser.add_argument("--zip", help="загрузить уже скачанный архив набора целиком")
    parser.add_argument("--make-slice", action="store_true", help="собрать срез из архива --zip по списку --inn")
    parser.add_argument("--inn", nargs="*", default=[])
    asyncio.run(main(parser.parse_args()))
