import Foundation

// MARK: - UserDefaults-backed Storage

@propertyWrapper
public struct AIStorage<T: Codable> {
    private let key: String
    private let defaultValue: T
    private let defaults = UserDefaults.standard

    public init(key: String, defaultValue: T) {
        self.key = key
        self.defaultValue = defaultValue
    }

    public var wrappedValue: T {
        get {
            guard let data = defaults.data(forKey: key) else {
                return defaultValue
            }
            return (try? JSONDecoder().decode(T.self, from: data)) ?? defaultValue
        }
        set {
            if let data = try? JSONEncoder().encode(newValue) {
                defaults.set(data, forKey: key)
            }
        }
    }
}

// MARK: - Settings

public struct AITranslationSettings {
    // Global master toggle
    @AIStorage(key: "ai_translation:enabled", defaultValue: false)
    public static var enabled: Bool

    // Proxy server URL
    @AIStorage(key: "ai_translation:proxy_url", defaultValue: "")
    public static var proxyServerURL: String

    // Per-chat enabled chat IDs
    @AIStorage(key: "ai_translation:enabled_chat_ids", defaultValue: [])
    public static var enabledChatIds: [Int64]

    // Directional toggles
    @AIStorage(key: "ai_translation:auto_incoming", defaultValue: true)
    public static var autoTranslateIncoming: Bool

    @AIStorage(key: "ai_translation:auto_outgoing", defaultValue: true)
    public static var autoTranslateOutgoing: Bool

    // Context mode: 1 = single message, 2 = conversation context
    @AIStorage(key: "ai_translation:context_mode", defaultValue: 1)
    public static var contextMode: Int

    // Number of context messages to send (when mode == 2)
    @AIStorage(key: "ai_translation:context_count", defaultValue: 20)
    public static var contextMessageCount: Int

    // Dev settings
    @AIStorage(key: "ai_translation:show_raw_responses", defaultValue: false)
    public static var showRawAPIResponses: Bool
}
