# Basic node tests on regnet
# Run with: python3 -m pytest -v or pytest -v
# The regnet server is started by conftest.py

import hashlib
from base64 import b64decode
from time import monotonic, sleep
from common import get_client


def test_port_regnet(myserver, verbose=False):
    client = get_client(verbose=verbose)
    data = client.command(command="portget")
    if verbose:
        print(f"portget returns {data}")
    assert int(data['port']) == 3030


def test_diff_json(myserver, verbose=False):
    client = get_client(verbose=verbose)
    data1 = client.command(command="difflast")
    if verbose:
        print(f"difflast returns {data1}")
    data2 = client.command(command="difflastjson")
    if verbose:
        print(f"difflastjson returns {data2}")
    block1 = data1[0]
    diff1 = data1[1]
    block2 = data2['block']
    diff2 = data2['difficulty']
    assert block1 == block2
    assert diff1 == diff2


def test_keygen_json(myserver, verbose=False):
    client = get_client(verbose=verbose)
    data1 = client.command(command="keygen")
    if verbose:
        print(f"keygen returns {data1}")
    data2 = client.command(command="keygenjson")
    if verbose:
        print(f"keygenjson returns {data2}")
    assert len(data1[1]) > 0
    assert len(data1[2]) > 0
    assert len(data1[1]) == len(data2['public_key'])
    assert len(data1[2]) == len(data2['address'])


def test_api_config(myserver, verbose=False):
    client = get_client(verbose=verbose)
    data = client.command(command="api_getconfig")
    if verbose:
        print(f"api_getconfig returns {data}")
    assert data['regnet'] is True
    # Do not enforce type. Old node sent string, this is an int. V2 returns an int (config is typed).
    # Voluntary break formal compatibility in favor of correct typing.
    assert int(data['port']) == 3030


def test_api_getaddresssince(myserver, verbose=False):
    client = get_client(verbose=verbose)
    client.command(command="regtest_generate", options=[1])  # Mine a block so that we have some funds
    tx_id = client.send(recipient=client.address, amount=1.0)  # Tries to send 1.0 to self
    client.command(command="regtest_generate", options=[1])  # Confirm the transaction
    confirmed_block = client.command(command="blocklastjson")
    target_height = confirmed_block['block_height'] + 8
    deadline = monotonic() + 15
    current_height = confirmed_block['block_height']
    while current_height < target_height and monotonic() < deadline:
        client.command(command="regtest_generate", options=[1])
        current_height = client.command(command="blocklastjson")['block_height']
    assert current_height >= target_height

    since = confirmed_block['block_height'] - 1
    conf = 8
    data = client.command(command="api_getaddresssince", options=[since, conf, client.address])
    if verbose:
        print(f"api_getaddresssince returns {data}")
    matching_transactions = [
        transaction
        for transaction in data['transactions']
        if transaction[5].startswith(tx_id)
    ]
    assert data['last'] == confirmed_block['block_height']
    assert len(matching_transactions) == 1


def test_api_getblockssince(myserver, verbose=False):
    client = get_client(verbose=verbose)
    client.command(command="regtest_generate", options=[1])  # Mine a block so that we have some funds
    data = '1234567890'
    amount = 1.5
    client.send(recipient=client.address, amount=amount, data=data)  # Tries to send amount to self
    client.command(command="regtest_generate", options=[10])  # Mine 10 more blocks
    sleep(1)
    data2 = client.command(command="blocklastjson")
    if verbose:
        print(f"blocklastjson returns {data2}")
    since = data2['block_height'] - 10
    blocks = client.command(command="api_getblocksince", options=[since])
    if verbose:
        print(f"api_getblocksince returns {blocks}")
    n = len(blocks)
    assert n == 11
    matching_transactions = [block for block in blocks if block[11] == data]
    assert len(matching_transactions) == 1
    assert float(matching_transactions[0][4]) == amount


def test_add_validate(myserver, verbose=False):
    client = get_client(verbose=verbose)
    data = client.command(command="addvalidate", options=[client.address])
    if verbose:
        print(f"addvalidate returns {data}")
    assert data == "valid"


def test_pubkey_address(myserver, verbose=False):
    client = get_client(verbose=verbose)
    client.command(command="regtest_generate", options=[1])  # Mine a block
    sleep(1)
    data = client.command(command="blocklastjson")
    if verbose:
        print(f"blocklastjson returns {data}")
    pubkey = b64decode(data['public_key']).decode('utf-8')
    if verbose:
        print("Pubkey", pubkey, type(pubkey))
    address = hashlib.sha224(pubkey.encode("utf-8")).hexdigest()
    assert address == client.address


if __name__ == "__main__":
    test_port_regnet(None, True)
    test_diff_json(None, True)
    test_keygen_json(None, True)
    test_api_config(None, True)
    test_api_getaddresssince(None, True)
    test_api_getblockssince(None, True)
    test_add_validate(None, True)
    test_pubkey_address(None, True)
