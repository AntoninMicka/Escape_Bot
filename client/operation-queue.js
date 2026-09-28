(function (root) {
    'use strict';

    class OperationQueue {
        constructor({storage, storageKey, createId, now = () => Date.now(), maxEntries = 50}) {
            this.storage = storage;
            this.storageKey = storageKey;
            this.createId = createId;
            this.now = now;
            this.maxEntries = maxEntries;
            this.entries = this._load();
        }

        enqueue(type, payload, sessionId, operationId = '') {
            const id = operationId || this.createId();
            const message = {type, payload: {...payload}, operation_id: id};
            this.entries = this.entries.filter(entry => entry.message.operation_id !== id);
            this.entries.push({session_id: sessionId, created_at: this.now(), message});
            if (this.entries.length > this.maxEntries) {
                this.entries = this.entries.slice(-this.maxEntries);
            }
            this._persist();
            return message;
        }

        acknowledge(operationId) {
            if (!operationId) return false;
            const previousLength = this.entries.length;
            this.entries = this.entries.filter(entry => entry.message.operation_id !== operationId);
            if (this.entries.length !== previousLength) this._persist();
            return this.entries.length !== previousLength;
        }

        pendingForSession(sessionId) {
            return this.entries
                .filter(entry => entry.session_id === sessionId)
                .map(entry => ({...entry.message, payload: {...entry.message.payload}}));
        }

        discardSession(sessionId) {
            const previousLength = this.entries.length;
            this.entries = this.entries.filter(entry => entry.session_id !== sessionId);
            if (this.entries.length !== previousLength) this._persist();
        }

        _load() {
            try {
                const parsed = JSON.parse(this.storage.getItem(this.storageKey) || '[]');
                if (!Array.isArray(parsed)) return [];
                return parsed.filter(entry =>
                    entry && typeof entry.session_id === 'string' &&
                    entry.message && typeof entry.message.type === 'string' &&
                    typeof entry.message.operation_id === 'string' &&
                    entry.message.operation_id.length >= 1 && entry.message.operation_id.length <= 128 &&
                    entry.message.payload && typeof entry.message.payload === 'object'
                ).slice(-this.maxEntries);
            } catch (_) {
                return [];
            }
        }

        _persist() {
            try {
                this.storage.setItem(this.storageKey, JSON.stringify(this.entries));
            } catch (_) {
                // The in-memory queue still protects retries during this page lifetime.
            }
        }
    }

    root.EscapeBotOperationQueue = OperationQueue;
    if (typeof module !== 'undefined' && module.exports) module.exports = {OperationQueue};
})(typeof globalThis !== 'undefined' ? globalThis : this);
