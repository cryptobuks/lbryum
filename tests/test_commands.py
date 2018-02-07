import unittest
import time
from collections import OrderedDict

from lbryschema.claim import ClaimDict
from lbryschema.signer import SECP256k1

from lbryum import commands, wallet, transaction, bip32, network, blockchain, lbrycrd, contacts
from lbryum.errors import NotEnoughFunds
from lbryum.constants import TYPE_ADDRESS, TYPE_CLAIM, TYPE_UPDATE, TYPE_SUPPORT, TYPE_SCRIPT
from test_data import SAMPLE_CLAIMS_FOR_NAME_RESULT, SAMPLE_CLAIMTRIE_GETVALUE_RESULT,\
    SAMPLE_CLAIMTRIE_GETVALUEFORURI_RESULT, SECP256K1_PRIVATE_KEY


PUBKEY = 'xpub661MyMwAqRbcF8M4CH68NvHEc6TUNaVhXwmGrsagNjrCja49H9L4ziJGe8YmaSBPbY4ZmQPQeW5CK6fiwx2EH6VxQab3zwDzZVWVApDSVNh'


class MocStore(dict):
    def put(self, key, val):
        self[key] = val


class Contacts(contacts.Contacts):
    def __init__(self):
        pass


class MocWallet(wallet.NewWallet):

    def __init__(self):
        super(MocWallet, self).__init__(MocStore())
        self.accounts = {'0': bip32.BIP32_Account({'xpub': PUBKEY})}
        self.send_tx_connected = True
        self.send_tx_success = True
        self.sent_transactions = []
        self.height = 0
        self.transactions = OrderedDict()

    @property
    def next_height(self):
        self.height += 1
        return self.height

    @property
    def last_transaction(self):
        return next(reversed(self.transactions.values()))

    def send_tx(self, tx, timeout=300):
        self.sent_transactions.append(tx)
        if not self.send_tx_connected:
            raise Exception("Not connected.")
        tx.raw = tx.serialize()
        return self.send_tx_success, tx.raw

    def sign_transaction(self, tx, password):
        for txi in tx._inputs:
            if 'signatures' not in txi:
                txi.update({
                    'height': self.next_height,
                    'signatures': [None],
                    'pubkeys': ['02e61d176da16edd1d258a200ad9759ef63adf8e14cd97f53227bae35cdb84d2f6'],
                    'x_pubkeys': ['02e61d176da16edd1d258a200ad9759ef63adf8e14cd97f53227bae35cdb84d2f6']
                })

    def add_address_transaction(self, amount):
        out_address = self.create_new_address()
        return self._add_transaction(
            out_address, amount,
            (TYPE_ADDRESS, out_address, amount)
        )

    def add_claim_transaction(self, name, amount, value=''):
        out_address = self.create_new_address()
        return self._add_transaction(
            out_address, amount,
            (TYPE_CLAIM | TYPE_SCRIPT, ((name, value), out_address), amount)
        )

    def add_support_transaction(self, name, amount, claim_id, claim_addr):
        out_address = self.create_new_address()
        return self._add_transaction(
            out_address, amount,
            (TYPE_ADDRESS | TYPE_SUPPORT, ((name, claim_id), claim_addr), amount)
        )

    def _add_transaction(self, out_address, out_amount, out_data):
        in_address = self.create_new_address()
        tx = transaction.Transaction.from_io(
            [{
                'address': in_address,
                'prevout_hash': '3140eb24b43386f35ba69e3875eb6c93130ac66201d01c58f598defc949a5c2a',
                'prevout_n': 0,
            }],
            [
                out_data
            ]
        )
        self.sign_transaction(tx, '')
        tx.raw = tx.serialize()
        tx_hash = tx.hash()
        tx_height = self.next_height
        self.history.setdefault(out_address, [])
        self.history[out_address].append([tx_hash, tx_height])
        self.txo[tx_hash] = {
            out_address: [(0, out_amount, False)]
        }
        self.transactions[tx_hash] = tx
        return tx

    def make_last_tx_verified(self):
        tx = self.last_transaction
        out_address = self.txo[tx.hash()].keys()[0]
        height = self.history[out_address][0][1]
        self.verified_tx[tx.hash()] = (height, time.time(), 1)


class MocBlockchain(blockchain.LbryCrd):

    def __init__(self, config, network):
        chain = self.BLOCKCHAIN_NAME
        params = blockchain.blockchain_params
        script_address = params[chain]['script_address']
        script_address_prefix = params[chain]['script_address_prefix']
        pubkey_address = params[chain]['pubkey_address']
        pubkey_address_prefix = params[chain]['pubkey_address_prefix']
        lbrycrd.SCRIPT_ADDRESS = (script_address, script_address_prefix)
        lbrycrd.PUBKEY_ADDRESS = (pubkey_address, pubkey_address_prefix)
        super(MocBlockchain, self).__init__(config, network)
        self.respond_with_header = None

    def read_header(self, block_height):
        return self.respond_with_header


class MocNetwork(network.Network):

    def __init__(self, responses=None):
        self.responses = responses or {}
        self.config = network.SimpleConfig({
            'lbryum_path': '.',
            'chain': 'lbrycrd_main'
        })
        self.default_server = 'lbry.io:50001:t'
        self.heights = {self.default_server: 1}
        self.blockchain = MocBlockchain(self.config, self)

    def send(self, request, callback):
        assert len(request) == 1, 'Mock network only supports one request at a time.'
        request = request[0]
        callback({'result': self.responses[request[0]](request[1])})


class MocCommands(commands.Commands):
    def __init__(self, config=None, wallet=None, network=None):
        self.config = config or {}
        self.wallet = wallet or MocWallet()
        self.network = network or MocNetwork()
        self.contacts = Contacts()
        self._password = None


class TestUtilCommands(unittest.TestCase):

    def test_commands(self):
        cmds = MocCommands()
        self.assertEqual(
            95, len(cmds.commands().split())
        )

    def test_locked(self):
        cmds = MocCommands()
        self.assertEqual(False, cmds.locked)
        cmds.wallet.use_encryption = True
        self.assertEqual(True, cmds.locked)
        cmds._password = 'foo'
        self.assertEqual(False, cmds.locked)

    @unittest.skip('todo: finish implementing')
    def test_lock_unlock(self):
        cmds = MocCommands()
        self.assertEqual(False, cmds.locked)
        cmds.wallet.use_encryption = True
        cmds.lock_wallet()
        self.assertEqual(True, cmds.locked)
        cmds.wallet.master_private_keys['x/'] = SECP256K1_PRIVATE_KEY
        cmds.wallet.master_public_keys['x/'] = SECP256K1_PRIVATE_KEY
        cmds.unlock_wallet('foo')
        self.assertEqual(False, cmds.locked)


class TestImportExportCertificateInfoCommand(unittest.TestCase):

    def _make_claim_tx_key(self, cmds):
        claim = ClaimDict.generate_certificate(SECP256K1_PRIVATE_KEY, curve=SECP256k1)
        cmds.wallet.add_address_transaction(4003002001000)
        tx = cmds.wallet.add_claim_transaction('lbry://@test', 1000, claim.serialized)

        cmds.network = MocNetwork({
            'blockchain.claimtrie.getclaimsbyids': lambda _: {
                tx.get_claim_id(0): cmds.wallet.get_name_claims()[0]
            }
        })
        key = cmds._serialize_certificate_key(tx.get_claim_id(0), SECP256K1_PRIVATE_KEY)
        return claim, tx, key

    def test_importcertificateinfo_no_args(self):
        self.assertEqual({}, MocCommands().importcertificateinfo())

    def test_importcertificateinfo(self):
        cmds = MocCommands()
        claim, tx, key = self._make_claim_tx_key(cmds)
        self.assertEqual(cmds.importcertificateinfo(key), {
            '84cdc6092acaaffe7f704766a3b3c83e369cb65f': {'success': True}
        })

    def test_importcertificateinfo_already_exists(self):
        cmds = MocCommands()
        claim, tx, key = self._make_claim_tx_key(cmds)
        cmds.wallet.save_certificate(tx.get_claim_id(0), SECP256K1_PRIVATE_KEY)
        self.assertEqual(cmds.importcertificateinfo(key), {
            '84cdc6092acaaffe7f704766a3b3c83e369cb65f': {
                'error': 'refusing to overwrite certificate key already in the wallet',
                'success': False
            }
        })

    def test_exportcertificateinfo(self):
        cmds = MocCommands()
        claim, tx, key = self._make_claim_tx_key(cmds)
        cmds.wallet.save_certificate(tx.get_claim_id(0), SECP256K1_PRIVATE_KEY)
        self.assertEqual(
            cmds.exportcertificateinfo(tx.get_claim_id(0)),
            '84cdc6092acaaffe7f704766a3b3c83e369cb65f2d2d2d2d2d424547494e204543'
            '2050524956415445204b45592d2d2d2d2d0a4d485143415145454950626a614566'
            '434343793548487647486b457733582f64544a586c72346a63454a4856314f6d63'
            '4244506d6f416347425375424241414b0a6f555144516741456c4c50726b564961'
            '7076744b727630446b67516239764158744351444249752b69486c735143356478'
            '315a6e4f575a7770594b51754d34690a4c4e6275546c667843485759776f76774c'
            '6a596e616f3869776770306f673d3d0a2d2d2d2d2d454e442045432050524956415'
            '445204b45592d2d2d2d2d0a'
        )


class TestGetBalanceCommand(unittest.TestCase):

    def test_getbalance_no_transactions(self):
        cmds = MocCommands()
        self.assertEqual({'confirmed': '0'}, cmds.getbalance())

    def test_getbalance(self):
        cmds = MocCommands()
        cmds.wallet.add_address_transaction(1000123000)
        cmds.wallet.add_claim_transaction('test', 5000123000)
        self.assertEqual({'confirmed': '60.00246'}, cmds.getbalance())


class TestPassthroughNetworkCommands(unittest.TestCase):

    def test_getblock(self):
        cmds = MocCommands()
        cmds.network = MocNetwork({
            'blockchain.block.get_block': lambda arg: arg
        })
        self.assertEqual(['the hash'], cmds.getblock('the hash'))

    def test_getclaimtrie(self):
        cmds = MocCommands()
        cmds.network = MocNetwork({
            'blockchain.claimtrie.get': lambda _: 'CLAIM TRIE'
        })
        self.assertEqual('CLAIM TRIE', cmds.getclaimtrie())


class TestGetTransactionCommand(unittest.TestCase):

    def test_gettransaction_local(self):
        cmds = MocCommands()
        tx = cmds.wallet.add_address_transaction(1)
        self.assertEqual(
            {'inputs', 'lockTime', 'outputs', 'version'},
            set(cmds.gettransaction(tx.hash()))
        )

    def test_gettransaction_network(self):
        tx = transaction.Transaction.from_io([], [])
        tx.raw = tx.serialize()
        tx_hash = tx.hash()
        cmds = MocCommands()
        cmds.wallet = None
        cmds.network = MocNetwork({
            'blockchain.transaction.get': lambda _: tx.raw
        })
        self.assertEqual(
            {'inputs': [], 'lockTime': 0, 'outputs': [], 'version': 1},
            cmds.gettransaction(tx_hash)
        )


class TestGetNameClaimsCommand(unittest.TestCase):

    def test_getnameclaims_no_claims(self):
        cmds = MocCommands()
        self.assertEqual([], cmds.getnameclaims())

    def test_getnameclaims_with_result(self):
        cmds = MocCommands()
        cmds.wallet.add_claim_transaction('test1', 1000123000)
        cmds.wallet.add_claim_transaction('test2', 5000123000)
        self.assertEqual(
            ['test1', 'test2'],
            [c['name'] for c in cmds.getnameclaims()]
        )


class TestGetClaimsForNameCommand(unittest.TestCase):

    def test_getclaimsforname_no_claims(self):
        cmds = MocCommands()
        cmds.network = MocNetwork({
            'blockchain.claimtrie.getclaimsforname': lambda _: {'claims': []}
        })
        self.assertEqual({'claims': []}, cmds.getclaimsforname('test'))

    def test_getclaimsforname(self):
        cmds = MocCommands()
        cmds.network = MocNetwork({
            'blockchain.claimtrie.getclaimsforname': lambda _: SAMPLE_CLAIMS_FOR_NAME_RESULT,
            'blockchain.claimtrie.getclaimbyid': lambda _: None
        })
        self.assertEqual(9, len(cmds.getclaimsforname('test')['claims']))


class TestGetClaimByIdCommand(unittest.TestCase):

    def test_getclaimbyid_no_claims(self):
        cmds = MocCommands()
        cmds.network = MocNetwork({
            'blockchain.claimtrie.getclaimbyid': lambda _: {}
        })
        self.assertEqual({}, cmds.getclaimbyid('test'))

    def test_getclaimbyid(self):
        cmds = MocCommands()
        cmds.network = MocNetwork({
            'blockchain.claimtrie.getclaimbyid': lambda _: SAMPLE_CLAIMS_FOR_NAME_RESULT
        })
        self.assertEqual(9, len(cmds.getclaimbyid('test')['claims']))


class TestGetClaimByOutpointCommand(unittest.TestCase):

    def test_getclaimbyoutpoint_no_claims(self):
        cmds = MocCommands()
        cmds.network = MocNetwork({
            'blockchain.claimtrie.getclaimsintx': lambda _: []
        })
        self.assertEqual(
            {'error': 'claim not found', 'outpoint': 'test:1', 'success': False},
            cmds.getclaimbyoutpoint('test', 1)
        )

    def test_getclaimbyoutpoint(self):
        cmds = MocCommands()
        cmds.network = MocNetwork({
            'blockchain.claimtrie.getclaimsintx': lambda _: SAMPLE_CLAIMS_FOR_NAME_RESULT['claims']
        })
        self.assertEqual(16, len(cmds.getclaimbyoutpoint('test', 1)))


class TestGetClaimsFromTxCommand(unittest.TestCase):

    def test_getclaimsfromtx_no_claims(self):
        cmds = MocCommands()
        cmds.network = MocNetwork({
            'blockchain.claimtrie.getclaimsintx': lambda _: []
        })
        self.assertEqual([], cmds.getclaimsfromtx('test'))

    def test_getclaimsfromtx(self):
        cmds = MocCommands()
        cmds.network = MocNetwork({
            'blockchain.claimtrie.getclaimsintx': lambda _: SAMPLE_CLAIMS_FOR_NAME_RESULT['claims']
        })
        self.assertEqual(SAMPLE_CLAIMS_FOR_NAME_RESULT['claims'], cmds.getclaimsfromtx('test'))


class TestGetCertificateClaimsCommand(unittest.TestCase):

    def test_getcertificateclaims_empty(self):
        cmds = MocCommands()
        cmds.wallet.add_address_transaction(4003002001000)
        cmds.wallet.add_claim_transaction('lbry://@test', 1000)
        self.assertEqual([], cmds.getcertificateclaims())

    def test_getcertificateclaims(self):
        cmds = MocCommands()
        claim = ClaimDict.generate_certificate(SECP256K1_PRIVATE_KEY, curve=SECP256k1)
        cmds.wallet.add_address_transaction(4003002001000)
        tx = cmds.wallet.add_claim_transaction('lbry://@test', 1000, claim.serialized)
        cmds.wallet.save_certificate(tx.get_claim_id(0), SECP256K1_PRIVATE_KEY)
        cmds.wallet.set_default_certificate(tx.get_claim_id(0))
        self.assertEqual(1, len(cmds.getcertificateclaims()))
        self.assertIn('certificate', cmds.getcertificateclaims()[0]['value'])


class TestGetCertificatesForSigningCommand(unittest.TestCase):

    def test_getcertificatesforsigning_empty(self):
        cmds = MocCommands()
        cmds.wallet.add_address_transaction(4003002001000)
        cmds.wallet.add_claim_transaction('lbry://@test', 1000)
        self.assertEqual([], cmds.getcertificatesforsigning())

    def test_getcertificatesforsigning(self):
        cmds = MocCommands()
        claim = ClaimDict.generate_certificate(SECP256K1_PRIVATE_KEY, curve=SECP256k1)
        cmds.wallet.add_address_transaction(4003002001000)
        tx = cmds.wallet.add_claim_transaction('lbry://@test', 1000, claim.serialized)
        cmds.wallet.save_certificate(tx.get_claim_id(0), SECP256K1_PRIVATE_KEY)
        cmds.wallet.set_default_certificate(tx.get_claim_id(0))
        self.assertEqual(1, len(cmds.getcertificatesforsigning()))
        self.assertIn('certificate', cmds.getcertificateclaims()[0]['value'])


class TestGetValueForNameCommand(unittest.TestCase):

    def setUp(self):
        self.cmds = MocCommands()
        self.cmds.network.default_server = 'lbryum8.lbry.io:50001:t'
        self.cmds.network.blockchain.local_height = 316209
        self.cmds.network.heights = {
            self.cmds.network.default_server: self.cmds.network.blockchain.local_height
        }
        self.cmds.network.blockchain.respond_with_header = {
            'nonce': 3669616010,
            'prev_block_hash': '2861f2474292fdad2e3e57bb07d59afd42eb3b17c96fa387ba31af09c6cd5220',
            'timestamp': 1517698627,
            'merkle_root': 'cee32cc073fb0f62ce78ef14d0cd5de852d3e9e6af1c4f748bf402a34dfb05f2',
            'claim_trie_root': '7e0e07df79b4eb7a3d1235ef03fb6a0bd2a581de8a33f570a9bffedb3afc3923',
            'version': 536870912,
            'bits': 436557565
        }

    def test_getvalueforname_no_value(self):
        self.cmds.network.responses = {
            'blockchain.claimtrie.getvalue': lambda _: {}
        }
        self.assertEqual({'error': 'proof not in result'}, self.cmds.getvalueforname('five'))

    def test_getvalueforname(self):
        self.cmds.network.responses = {
            'blockchain.claimtrie.getvalue': lambda _: SAMPLE_CLAIMTRIE_GETVALUE_RESULT
        }
        self.assertEqual(
            {'address', 'amount', 'claim_id', 'claim_sequence', 'decoded_claim', 'depth',
             'effective_amount', 'has_signature', 'height', 'name', 'nout',
             'permanent_url', 'supports', 'txid', 'value'},
            set(self.cmds.getvalueforname('five'))
        )


class TestGetValueForUriCommand(unittest.TestCase):

    def setUp(self):
        self.cmds = MocCommands()
        self.cmds.network.blockchain.local_height = 317927
        self.cmds.network.heights = {
            self.cmds.network.default_server: self.cmds.network.blockchain.local_height
        }
        self.cmds.network.blockchain.respond_with_header = {
            'nonce': 3350083195,
            'prev_block_hash': 'b9317a536af52914a000ebfeaf2b5353bac4c615d6de9bdc19459df9c91ffc5b',
            'timestamp': 1517971678,
            'merkle_root': '01a65e2fed60beb1c2375c521b2db31abfcb25685436fd35fab8ac1afd97e9b9',
            'claim_trie_root': '8cf7a34f08a731334cc8473e18115ce81e59fec753f1bc6c73d0f8b493705ba5',
            'version': 536870912,
            'bits': 436486851
        }

    def test_getvalueforuri_no_value(self):
        self.cmds.network.responses = {
            'blockchain.claimtrie.getvaluesforuris': lambda _: {}
        }
        self.assertEqual({}, self.cmds.getvalueforuri('lbry://five'))
        self.assertEqual({}, self.cmds.getvaluesforuris('lbry://five'))

    def test_getvalueforuri(self):
        self.cmds.network.responses = {
            'blockchain.claimtrie.getvaluesforuris': lambda _: SAMPLE_CLAIMTRIE_GETVALUEFORURI_RESULT
        }
        self.assertEqual({'claim'}, set(self.cmds.getvalueforuri('lbry://five')))
        self.assertEqual({u'lbry://five'}, set(self.cmds.getvaluesforuris('lbry://five')))


class TestListAddressesCommand(unittest.TestCase):

    def test_listaddresses_no_value(self):
        cmds = MocCommands()
        out = cmds.listaddresses()
        self.assertEqual([], out)

    def test_listaddresses(self):
        cmds = MocCommands()
        cmds.wallet.create_new_address()
        out = cmds.listaddresses()
        self.assertEqual(['bScaWvgzAzFXzAcVgDDARfo9RFhdrm4pVc'], out)


class TestListUnspentCommand(unittest.TestCase):

    def test_listunspent_no_value(self):
        cmds = MocCommands()
        cmds.wallet.create_new_address()
        self.assertEqual([], cmds.listunspent())

    def test_listunspent(self):
        cmds = MocCommands()
        cmds.wallet.create_new_address()
        cmds.wallet.add_address_transaction(110000000)
        self.assertEqual([{
            'address': 'bMF18XkZ6K9JT172dA4DxxQK92Q7XrQxCL',
            'coinbase': False,
            'height': 2,
            'is_claim': False,
            'is_support': False,
            'is_update': False,
            'prevout_hash': 'df303881e9014cce89c7acf55b124372e22979284baa99bb9fa178a9d35c97cb',
            'prevout_n': 0,
            'value': 1.1
        }], cmds.listunspent())


class TestGetPubKeysCommand(unittest.TestCase):

    def test_getpubkeys(self):
        cmds = MocCommands()
        address = cmds.wallet.create_new_address()
        self.assertEqual(
            ['02f0eaac8dde84cf80ebdb3b136cb29d8c7954c869c6c8fdf9d72a82323a72a30e'],
            cmds.getpubkeys(address)
        )


class TestIsMineCommand(unittest.TestCase):

    def test_ismine_yes(self):
        cmds = MocCommands()
        address = cmds.wallet.create_new_address()
        self.assertEqual(True, cmds.ismine(address))

    def test_ismine_no(self):
        cmds = MocCommands()
        cmds.wallet.create_new_address()
        self.assertEqual(False, cmds.ismine('deadbeef'*12))


class TestClaimHistoryCommand(unittest.TestCase):

    def test_claimhistory_empty(self):
        cmds = MocCommands()
        cmds.wallet.create_new_address()
        self.assertEqual([], cmds.claimhistory())

    def test_claimhistory(self):
        cmds = MocCommands()
        cmds.wallet.add_address_transaction(510000000)
        cmds.wallet.make_last_tx_verified()
        tx = cmds.wallet.add_claim_transaction('test', 310000000)
        cmds.wallet.make_last_tx_verified()
        cmds.wallet.add_support_transaction(
            'test', 110000000, tx.get_claim_id(0), "bRcHraa8bYJZL7vkh5sNmGwPDERFUjGPP9"
        )
        cmds.wallet.make_last_tx_verified()
        self.assertEqual([5.1, 3.1, 1.1], [h['value'] for h in cmds.claimhistory()])


class TestPayToCommand(unittest.TestCase):

    def test_payto_success(self):
        cmds = MocCommands()
        cmds.wallet.add_address_transaction(510000000)
        cmds.wallet.create_new_address(for_change=True)
        destination = cmds.wallet.create_new_address()
        out = cmds.payto([(destination, 1)])
        self.assertEqual(True, out['success'])

    def test_payto_throws_not_enough_funds(self):
        cmds = MocCommands()
        cmds.wallet.add_address_transaction(510000000)
        cmds.wallet.create_new_address(for_change=True)
        destination = cmds.wallet.create_new_address()
        with self.assertRaises(NotEnoughFunds):
            cmds.payto([(destination, 510000)])


class TestClaimCommand(unittest.TestCase):

    def test_claim_success(self):
        cmds = MocCommands()
        cmds.wallet.add_address_transaction(110000000)
        out = cmds.claim('test', 'value', 1, skip_validate_schema=True, raw=True)
        self.assertEqual(True, out['success'])

    def test_claim_not_enough_funds(self):
        cmds = MocCommands()
        out = cmds.claim('test', '[payload]', 1, skip_validate_schema=True, raw=True)
        self.assertEqual(False, out['success'])
        self.assertEqual('Not enough funds', out['reason'])


class TestRenewClaimCommand(unittest.TestCase):

    def test_renewclaim_success(self):
        cmds = MocCommands()
        cmds.wallet.add_address_transaction(510000000)
        tx = cmds.wallet.add_claim_transaction('test', 100200)
        out = cmds.renewclaim(tx.hash(), 0, skip_validate_schema=True)
        self.assertEqual(True, out['success'])

    def test_renewclaim_fee_more_than_original_bid(self):
        cmds = MocCommands()
        cmds.wallet.add_address_transaction(510000000)
        tx = cmds.wallet.add_claim_transaction('test', 10)
        out = cmds.renewclaim(tx.hash(), 0, skip_validate_schema=True)
        self.assertEqual(False, out['success'])
        self.assertEqual('Fee will exceed amount available in original bid. Increase amount', out['reason'])


class TestRenewClaimBeforeExpirationCommand(unittest.TestCase):

    def test_renewclaimbeforeexpiration_success(self):
        cmds = MocCommands()
        cmds.wallet.add_address_transaction(510000000)
        cmds.wallet.add_claim_transaction('test', 100200)
        out = cmds.renewclaimsbeforeexpiration(270000, skip_validate_schema=True)
        self.assertEqual(1, len(out.values()))
        self.assertEqual(True, out.values()[0]['success'])

    def test_renewclaimbeforeexpiration_nothing_renewed(self):
        cmds = MocCommands()
        cmds.wallet.add_address_transaction(510000000)
        cmds.wallet.add_claim_transaction('test', 100200)
        out = cmds.renewclaimsbeforeexpiration(260000, skip_validate_schema=True)
        self.assertEqual(0, len(out.values()))


class TestClaimCertificateCommand(unittest.TestCase):

    def test_claimcertificate_success(self):
        cmds = MocCommands()
        cmds.wallet.add_address_transaction(4003002001000)
        out = cmds.claimcertificate('lbry://@test', 1000)
        self.assertEqual(True, out['success'])

    def test_claim_not_enough_funds(self):
        cmds = MocCommands()
        cmds.wallet.add_address_transaction(3002001000)
        out = cmds.claimcertificate('lbry://@test', 1000)
        self.assertEqual(False, out['success'])
        self.assertEqual('Not enough funds', out['reason'])


class TestUpdateCommand(unittest.TestCase):

    def test_update_success(self):
        cmds = MocCommands()
        cmds.wallet.add_address_transaction(510000000)
        cmds.wallet.add_claim_transaction('test', 1)
        out = cmds.update('test', '[payload]', amount=1, tx_fee=1, skip_validate_schema=True, raw=True)
        self.assertEqual(True, out['success'])

    def test_update_not_enough_funds(self):
        cmds = MocCommands()
        cmds.wallet.add_address_transaction(110000000)
        cmds.wallet.add_claim_transaction('test', 1)
        out = cmds.update('test', '[payload]', amount=1, tx_fee=1, skip_validate_schema=True, raw=True)
        self.assertEqual(False, out['success'])
        self.assertEqual('Not enough funds', out['reason'])

    def test_update_not_found(self):
        cmds = MocCommands()
        cmds.wallet.add_address_transaction(510000000)
        cmds.wallet.add_claim_transaction('test', 1)
        out = cmds.update('foo', '[payload]', amount=1, tx_fee=1, skip_validate_schema=True, raw=True)
        self.assertEqual(False, out['success'])
        self.assertEqual('No claim to update', out['reason'])


class TestSendClaimToAddressCommand(unittest.TestCase):

    def test_sendclaimtoaddress_success(self):
        cmds = MocCommands()
        cmds.wallet.add_address_transaction(510000000)
        tx = cmds.wallet.add_claim_transaction('test', 1)
        destination = cmds.wallet.create_new_address()
        out = cmds.sendclaimtoaddress(tx.get_claim_id(0), destination, 1, skip_validate_schema=True)
        self.assertEqual(True, out['success'])

    def test_sendclaimtoaddress_not_enough_funds(self):
        cmds = MocCommands()
        cmds.wallet.add_address_transaction(1000)
        tx = cmds.wallet.add_claim_transaction('test', 1)
        destination = cmds.wallet.create_new_address()
        out = cmds.sendclaimtoaddress(tx.get_claim_id(0), destination, 1, skip_validate_schema=True)
        self.assertEqual(False, out['success'])
        self.assertEqual('Not enough funds', out['reason'])

    def test_sendclaimtoaddress_not_found(self):
        cmds = MocCommands()
        cmds.wallet.add_address_transaction(510000000)
        cmds.wallet.add_claim_transaction('test', 1)
        destination = cmds.wallet.create_new_address()
        out = cmds.sendclaimtoaddress('invalid', destination, 1, skip_validate_schema=True)
        self.assertEqual(False, out['success'])
        self.assertEqual('claim not found', out['reason'])


class TestSupportCommand(unittest.TestCase):

    def test_support_success(self):
        cmds = MocCommands()
        cmds.wallet.add_address_transaction(510000000)
        tx = cmds.wallet.add_claim_transaction('test', 1)
        out = cmds.support('test', tx.get_claim_id(0), 1, tx_fee=1)
        self.assertEqual(True, out['success'])

    def test_support_invalid_claim_id(self):
        cmds = MocCommands()
        cmds.wallet.add_address_transaction(10000000)
        out = cmds.support('test', 'deadbeef', 1, tx_fee=1)
        self.assertEqual(False, out['success'])
        self.assertEqual('Invalid claim id', out['reason'])

    def test_support_not_enough_funds(self):
        cmds = MocCommands()
        cmds.wallet.add_address_transaction(10000000)
        tx = cmds.wallet.add_claim_transaction('test', 1)
        out = cmds.support('test', tx.get_claim_id(0), 1, tx_fee=1)
        self.assertEqual(False, out['success'])
        self.assertEqual('Not enough funds', out['reason'])


class TestSendWithSupportCommand(unittest.TestCase):

    def test_sendwithsupport_success(self):
        cmds = MocCommands()
        cmds.wallet.add_address_transaction(510000000)
        tx = cmds.wallet.add_claim_transaction('test', 1)
        cmds.network = MocNetwork({
            'blockchain.claimtrie.getclaimbyid': lambda _: SAMPLE_CLAIMS_FOR_NAME_RESULT['claims'][0]
        })
        out = cmds.sendwithsupport(tx.get_claim_id(0), 1)
        self.assertEqual(True, out['success'])


class TestAbandonCommand(unittest.TestCase):

    def abandon_claim_with_name_value(self, name, satoshis, cmds=None):
        cmds = cmds or MocCommands()
        cmds.wallet.create_new_address(for_change=True)
        tx = cmds.wallet.add_claim_transaction(name, satoshis)
        return cmds.abandon(claim_id=tx.get_claim_id(0))

    def test_abandon_success(self):
        out = self.abandon_claim_with_name_value('test', 10000)
        self.assertEqual(True, out['success'])

    def test_abandon_fails_for_tiny_claim(self):
        out = self.abandon_claim_with_name_value('test', 1000)
        self.assertEqual(False, out['success'])
        self.assertEqual('transaction fee exceeds amount available', out['reason'])

    def test_abandon_fails_for_tiny_claim_and_not_enough_other_funds(self):
        cmds = MocCommands()
        cmds.wallet.add_address_transaction(500)
        out = self.abandon_claim_with_name_value('test', 1000, cmds)
        self.assertEqual(False, out['success'])
        self.assertEqual('transaction fee exceeds amount available', out['reason'])

    def test_abandon_success_for_tiny_claim_with_enough_other_funds(self):
        cmds = MocCommands()
        cmds.wallet.add_address_transaction(12000)
        cmds.wallet.add_address_transaction(12000)
        out = self.abandon_claim_with_name_value('test', 1000, cmds)
        self.assertEqual(True, out['success'])
        sent = cmds.wallet.sent_transactions[0]
        self.assertEqual(len(sent._inputs), 3)
        self.assertEqual(sent._inputs[0]['value'], 1000)
        self.assertEqual(sent._inputs[1]['value'], 12000)
        self.assertEqual(sent._inputs[2]['value'], 12000)
        self.assertEqual(len(sent._outputs), 1)
        self.assertEqual(sent._outputs[0][2], 600)


class FormatTests(unittest.TestCase):

    def test_format_lbrycrd_keys(self):
        a = {'amount': 100000000}
        out = commands.format_amount_value(a)
        self.assertEqual(1.0, out['amount'])
