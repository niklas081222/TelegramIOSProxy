import Foundation
import Postbox

public final class TranslationCache {
    private var cache: [MessageId: String] = [:]
    private var accessOrder: [MessageId] = []
    private let maxSize: Int
    private let lock = NSLock()

    public init(maxSize: Int = 500) {
        self.maxSize = maxSize
    }

    public func get(_ messageId: MessageId) -> String? {
        lock.lock()
        defer { lock.unlock() }

        guard let translation = cache[messageId] else {
            return nil
        }

        // Move to end of access order (most recently used)
        if let index = accessOrder.firstIndex(of: messageId) {
            accessOrder.remove(at: index)
            accessOrder.append(messageId)
        }

        return translation
    }

    public func set(_ messageId: MessageId, translation: String) {
        lock.lock()
        defer { lock.unlock() }

        if cache[messageId] != nil {
            // Update existing entry
            cache[messageId] = translation
            if let index = accessOrder.firstIndex(of: messageId) {
                accessOrder.remove(at: index)
                accessOrder.append(messageId)
            }
        } else {
            // Add new entry
            if accessOrder.count >= maxSize {
                // Evict least recently used
                let evicted = accessOrder.removeFirst()
                cache.removeValue(forKey: evicted)
            }
            cache[messageId] = translation
            accessOrder.append(messageId)
        }
    }

    public func clear() {
        lock.lock()
        defer { lock.unlock() }

        cache.removeAll()
        accessOrder.removeAll()
    }

    public var count: Int {
        lock.lock()
        defer { lock.unlock() }
        return cache.count
    }
}
