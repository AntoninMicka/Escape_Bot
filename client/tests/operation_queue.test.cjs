const assert = require('node:assert/strict');
const {OperationQueue} = require('../operation-queue.js');

class MemoryStorage {
    constructor() { this.values = new Map(); }
    getItem(key) { return this.values.get(key) || null; }
    setItem(key, value) { this.values.set(key, value); }
}

const storage = new MemoryStorage();
let sequence = 0;
const options = {
    storage,
    storageKey: 'operations:test-client',
    createId: () => `operation-${++sequence}`,
    now: () => 1234,
};

const queue = new OperationQueue(options);
const first = queue.enqueue('puzzle.submit', {puzzle_id: 'one', answer: '42'}, 'session-1');
assert.equal(first.operation_id, 'operation-1');
assert.deepEqual(queue.pendingForSession('session-1'), [first]);

const restored = new OperationQueue(options);
assert.equal(restored.pendingForSession('session-1')[0].operation_id, first.operation_id);
assert.deepEqual(restored.pendingForSession('another-session'), []);

const retry = restored.pendingForSession('session-1')[0];
assert.equal(retry.operation_id, first.operation_id);
assert.equal(restored.acknowledge(first.operation_id), true);
assert.deepEqual(restored.pendingForSession('session-1'), []);
assert.equal(restored.acknowledge(first.operation_id), false);

restored.enqueue('room.unlock', {pin: '1234'}, 'session-1');
restored.discardSession('session-1');
assert.deepEqual(restored.pendingForSession('session-1'), []);

console.log('operation queue tests passed');
