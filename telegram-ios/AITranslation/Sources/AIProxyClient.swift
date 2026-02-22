import Foundation
import SwiftSignalKit

// MARK: - Models

public struct AITranslateRequest: Codable {
    public let text: String
    public let direction: String
    public let chatId: String
    public let context: [AIContextMessage]

    enum CodingKeys: String, CodingKey {
        case text
        case direction
        case chatId = "chat_id"
        case context
    }

    public init(text: String, direction: String, chatId: String, context: [AIContextMessage]) {
        self.text = text
        self.direction = direction
        self.chatId = chatId
        self.context = context
    }
}

public struct AIContextMessage: Codable {
    public let role: String  // "me" or "them"
    public let text: String

    public init(role: String, text: String) {
        self.role = role
        self.text = text
    }
}

public struct AITranslateResponse: Codable {
    public let translatedText: String
    public let originalText: String
    public let direction: String
    public let translationFailed: Bool

    enum CodingKeys: String, CodingKey {
        case translatedText = "translated_text"
        case originalText = "original_text"
        case direction
        case translationFailed = "translation_failed"
    }
}

public struct AIHealthResponse: Codable {
    public let status: String
    public let uptimeSeconds: Double
    public let lastSuccessfulTranslation: Double?

    enum CodingKeys: String, CodingKey {
        case status
        case uptimeSeconds = "uptime_seconds"
        case lastSuccessfulTranslation = "last_successful_translation"
    }
}

public enum AITranslationError: Error {
    case networkError(Error)
    case serverError(Int)
    case decodingError
    case invalidURL
    case timeout
}

// MARK: - Proxy Client

public final class AIProxyClient {
    private let session: URLSession
    private let baseURL: String

    public init(baseURL: String) {
        self.baseURL = baseURL.hasSuffix("/") ? String(baseURL.dropLast()) : baseURL
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 20
        config.timeoutIntervalForResource = 25
        self.session = URLSession(configuration: config)
    }

    // MARK: - Translate

    public func translate(
        text: String,
        direction: String,
        chatId: Int64,
        context: [AIContextMessage]
    ) -> Signal<String, NoError> {
        guard let url = URL(string: "\(baseURL)/translate") else {
            return .single(text)
        }

        let request = AITranslateRequest(
            text: text,
            direction: direction,
            chatId: String(chatId),
            context: context
        )

        return Signal { subscriber in
            var urlRequest = URLRequest(url: url)
            urlRequest.httpMethod = "POST"
            urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")

            do {
                urlRequest.httpBody = try JSONEncoder().encode(request)
            } catch {
                subscriber.putNext(text)
                subscriber.putCompletion()
                return EmptyDisposable
            }

            let task = self.session.dataTask(with: urlRequest) { data, response, error in
                if let error = error {
                    if AITranslationSettings.showRawAPIResponses {
                        print("[AITranslation] Network error: \(error)")
                    }
                    subscriber.putNext(text)
                    subscriber.putCompletion()
                    return
                }

                guard let data = data else {
                    subscriber.putNext(text)
                    subscriber.putCompletion()
                    return
                }

                if AITranslationSettings.showRawAPIResponses {
                    if let rawString = String(data: data, encoding: .utf8) {
                        print("[AITranslation] Raw response: \(rawString)")
                    }
                }

                do {
                    let response = try JSONDecoder().decode(AITranslateResponse.self, from: data)
                    if response.translationFailed {
                        subscriber.putNext(text)
                    } else {
                        subscriber.putNext(response.translatedText)
                    }
                } catch {
                    subscriber.putNext(text)
                }
                subscriber.putCompletion()
            }

            task.resume()

            return ActionDisposable {
                task.cancel()
            }
        }
    }

    // MARK: - Health Check

    public func healthCheck() -> Signal<Bool, NoError> {
        guard let url = URL(string: "\(baseURL)/health") else {
            return .single(false)
        }

        return Signal { subscriber in
            let task = self.session.dataTask(with: url) { data, response, error in
                if let _ = error {
                    subscriber.putNext(false)
                    subscriber.putCompletion()
                    return
                }

                guard let httpResponse = response as? HTTPURLResponse else {
                    subscriber.putNext(false)
                    subscriber.putCompletion()
                    return
                }

                subscriber.putNext(httpResponse.statusCode == 200)
                subscriber.putCompletion()
            }
            task.resume()

            return ActionDisposable {
                task.cancel()
            }
        }
    }
}
