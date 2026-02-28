import Foundation
import SwiftSignalKit
import TelegramCore

/// Implements Telegram's ExperimentalInternalTranslationService protocol
/// to hook our AI translation into the existing translation infrastructure.
/// This plugs into the built-in message translation pipeline with zero
/// modifications to the message rendering code.
public final class AIExperimentalTranslationService: ExperimentalInternalTranslationService {
    public init() {}

    public func translate(
        texts: [AnyHashable: String],
        fromLang: String,
        toLang: String
    ) -> Signal<[AnyHashable: String]?, NoError> {
        // No-op: return empty success to prevent Telegram's batch pipeline from
        // actually translating. Our streaming catch-up handles all translations.
        // Returning [:] (not nil) prevents Telegram from falling back to cloud translation.
        return .single([:])
    }
}

/// Call this during app initialization to register the AI translation service.
public func registerAITranslationService() {
    engineExperimentalInternalTranslationService = AIExperimentalTranslationService()
}

/// Call this when the global toggle changes to enable/disable the service.
public func updateAITranslationServiceRegistration() {
    if AITranslationSettings.enabled {
        engineExperimentalInternalTranslationService = AIExperimentalTranslationService()
    } else {
        engineExperimentalInternalTranslationService = nil
    }
}
