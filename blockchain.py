import hashlib
import json
from time import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from uuid import uuid4

import requests
from flask import Flask, jsonify, request

import os
import pickle
import signal

# Signal Handler
def signal_handler(signum, frame):
    # Data persistence before exiting
    persist()
    exit()

# Data persistence
def persist():
    blockchain_file = open('./blockchain.data', 'wb')
    pickle.dump(blockchain, blockchain_file, -1)
    blockchain_file.close()

# 默认单线程同步阻塞方式处理请求,因此不用考虑线程安全问题
class Blockchain:
    def __init__(self):
        self.current_transactions = []
        self.chain = []
        self.nodes = set()

        # 创建创世块
        self.new_block(previous_hash='1', proof=100, is_persist=False, data={})

    def register_node(self, address: str) -> None:
        """
        Add a new node to the list of nodes

        :param address: Address of node. Eg. 'http://192.168.0.5:5000'
        """

        parsed_url = urlparse(address)
        self.nodes.add(parsed_url.netloc)
   
        persist()

    def valid_chain(self, chain: List[Dict[str, Any]]) -> bool:
        """
        Determine if a given blockchain is valid

        :param chain: A blockchain
        :return: True if valid, False if not
        """

        last_block = chain[0]
        current_index = 1

        last_hash = last_block['hash']
        last_block['hash'] = ''
        if self.hash(last_block) != last_hash:
            return False 
        last_block['hash'] = last_hash

        while current_index < len(chain):
            block = chain[current_index]
            print(f'{last_block}')
            print(f'{block}')
            print("\n-----------\n")
            # Check that the hash of the block is correct
            hash = block['hash']
            block['hash'] = ''
            if self.hash(block) != hash:
                return False
            block['hash'] = hash
            if block['previous_hash'] != last_block['hash']:
                return False

            # Check that the Proof of Work is correct
            if not self.valid_proof(last_block['proof'], block['proof']):
                return False

            last_block = block
            current_index += 1

        return True

    def resolve_conflicts(self) -> bool:
        """
        共识算法解决冲突
        使用网络中最长的链.

        :return:  如果链被取代返回 True, 否则为False
        """

        neighbours = self.nodes
        new_chain = None

        # We're only looking for chains longer than ours
        max_length = len(self.chain)

        # Grab and verify the chains from all the nodes in our network
        for node in neighbours:
            response = requests.get(f'http://{node}/chain')

            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']

                # Check if the length is longer and the chain is valid
                if length > max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain

        # Replace our chain if we discovered a new, valid chain longer than ours
        if new_chain:
            self.chain = new_chain
            return True

        persist()

        return False

    def new_block(self, proof: int, previous_hash: Optional[str], is_persist: bool, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成新块

        :param proof: The proof given by the Proof of Work algorithm
        :param previous_hash: Hash of previous Block
        :return: New Block
        """

        block = {
            'index': len(self.chain) + 1,
            'timestamp': time(),
            'transactions': self.current_transactions,
            'proof': proof,
            'previous_hash': previous_hash or self.chain[-1]['hash'],
            'hash': '',
            'node': node_identifier,
            'data': data
        }

        block['hash'] = self.hash(block)

        # Reset the current list of transactions
        self.current_transactions = []

        self.chain.append(block)

        if is_persist:
            persist()

        return block

    def new_transaction(self, sender: str, recipient: str, amount: int) -> int:
        """
        生成新交易信息，信息将加入到下一个待挖的区块中

        :param sender: Address of the Sender
        :param recipient: Address of the Recipient
        :param amount: Amount
        :return: The index of the Block that will hold this transaction
        """
        self.current_transactions.append({
            'sender': sender,
            'recipient': recipient,
            'amount': amount,
        })

        persist()

        return self.last_block['index'] + 1

    @property
    def last_block(self) -> Dict[str, Any]:
        return self.chain[-1]

    @staticmethod
    def hash(block: Dict[str, Any]) -> str:
        """
        生成块的 SHA-256 hash值

        :param block: Block
        """

        # We must make sure that the Dictionary is Ordered, or we'll have inconsistent hashes
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def proof_of_work(self, last_proof: int) -> int:
        """
        简单的工作量证明:
         - 查找一个 p' 使得 hash(pp') 以4个0开头
         - p 是上一个块的证明,  p' 是当前的证明
        """

        proof = 0
        while self.valid_proof(last_proof, proof) is False:
            proof += 1

        return proof

    @staticmethod
    def valid_proof(last_proof: int, proof: int) -> bool:
        """
        验证证明: 是否hash(last_proof, proof)以4个0开头

        :param last_proof: Previous Proof
        :param proof: Current Proof
        :return: True if correct, False if not.
        """

        guess = f'{last_proof}{proof}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"

    def get_block(self, hash: str) -> Dict[str, Any]:
        current_index = 0
        chain = self.chain
        chain_len = len(chain)
        while current_index < chain_len:
            block = chain[current_index]
            if block['hash'] == hash:
                return block

            current_index += 1

    def reset_chain(self) -> None:
        self.current_transactions = []
        self.chain = []

        # 创建创世块
        self.new_block(previous_hash='1', proof=100, is_persist=True, data={})

# Instantiate the Node
app = Flask(__name__)

# Generate a globally unique address for this node
node_identifier = str(uuid4()).replace('-', '')

# Handle Signal
signal.signal(signal.SIGINT, signal_handler)

# Instantiate the Blockchain
if os.path.exists('./blockchain.data'):
   blockchain_file = open('./blockchain.data', 'rb')
   blockchain = pickle.load(blockchain_file)
   blockchain_file.close()
else:
   blockchain = Blockchain()

@app.route('/mine', methods=['POST'])
def mine():
    # We run the proof of work algorithm to get the next proof...
    last_block = blockchain.last_block
    last_proof = last_block['proof']
    proof = blockchain.proof_of_work(last_proof)

    # 给工作量证明的节点提供奖励.
    # 发送者为 "0" 表明是新挖出的币
    blockchain.new_transaction(
        sender="0",
        recipient=node_identifier,
        amount=1,
    )

    # Forge the new Block by adding it to the chain
    block = blockchain.new_block(proof, None, True, data=request.get_json())

    response = {
        'message': "New Block Forged",
        'hash': block['hash'],
        'index': block['index'],
        'transactions': block['transactions'],
        'proof': block['proof'],
        'previous_hash': block['previous_hash'],
        'node': node_identifier,
        'data': block['data']
    }
    return jsonify(response), 200


@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    values = request.get_json()

    # 检查POST数据
    required = ['sender', 'recipient', 'amount']
    if not all(k in values for k in required):
        return 'Missing values', 400

    # Create a new Transaction
    index = blockchain.new_transaction(values['sender'], values['recipient'], values['amount'])

    response = {'message': f'Transaction will be added to Block {index}'}
    return jsonify(response), 200


@app.route('/chain', methods=['GET'])
def full_chain():
    response = {
        'chain': blockchain.chain,
        'length': len(blockchain.chain),
    }
    return jsonify(response), 200


@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    values = request.get_json()

    nodes = values.get('nodes')
    if nodes is None:
        return "Error: Please supply a valid list of nodes", 400

    for node in nodes:
        blockchain.register_node(node)

    response = {
        'message': 'New nodes have been added',
        'total_nodes': list(blockchain.nodes),
    }
    return jsonify(response), 200


@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    replaced = blockchain.resolve_conflicts()

    if replaced:
        response = {
            'message': 'Our chain was replaced',
            'new_chain': blockchain.chain
        }
    else:
        response = {
            'message': 'Our chain is authoritative',
            'chain': blockchain.chain
        }

    return jsonify(response), 200

@app.route('/block/get', methods=['GET'])
def get_block():
    block = blockchain.get_block(hash=request.args.get('hash'))
    return jsonify(block), 200

@app.route('/chain/reset', methods=['GET'])
def reset_chain():
    blockchain.reset_chain()
    response = {
        'chain': blockchain.chain,
        'length': len(blockchain.chain),
    }
    return jsonify(response), 200

if __name__ == '__main__':
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument('-p', '--port', default=5000, type=int, help='port to listen on')
    parser.add_argument('-addr', '--addr', default='127.0.0.1', type=str, help='host to listen on')
    args = parser.parse_args()
    port = args.port
    addr = args.addr

    app.run(host=addr, port=port)
