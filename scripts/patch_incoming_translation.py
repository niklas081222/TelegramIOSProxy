#!/usr/bin/env python3
"""Patch ChatControllerLoadDisplayNode.swift for translation rendering + streaming catch-up.

Sets translationState(isEnabled: true) so Telegram's rendering code activates translation
display. The actual translation is handled by our streaming catch-up (not Telegram's batch
pipeline — AIExperimentalTranslationService is a no-op that returns empty results).
"""
import sys
import re


def patch_incoming_translation(filepath: str) -> None:
    with open(filepath, "r") as f:
        content = f.read()

    # Target line: presentationInterfaceState = presentationInterfaceState.updatedTranslationState(contentData.state.translationState)
    # We add our override right after it.

    target = "presentationInterfaceState = presentationInterfaceState.updatedTranslationState(contentData.state.translationState)"

    if target not in content:
        print("ERROR: Could not find updatedTranslationState line")
        print("Incoming auto-translation will NOT work.")
        return

    override_code = """presentationInterfaceState = presentationInterfaceState.updatedTranslationState(contentData.state.translationState)

            // AI Translation: enable translation rendering (skip bot chats)
            if AITranslationSettings.enabled && AITranslationSettings.autoTranslateIncoming {
                if case let .peer(chatPeerId) = self.chatLocation {
                    let aiPeerId64 = chatPeerId.id._internalGetInt64Value()

                    // Quick sync check: skip known bot chats
                    if AIBackgroundTranslationObserver.botChatIds.contains(aiPeerId64) {
                        // Known bot — skip translation entirely
                    } else {
                        let existingState = presentationInterfaceState.translationState
                        if existingState == nil || existingState?.isEnabled != true {
                            presentationInterfaceState = presentationInterfaceState.updatedTranslationState(
                                ChatPresentationTranslationState(isEnabled: true, fromLang: "de", toLang: "en")
                            )
                            DispatchQueue.main.async { [weak self] in
                                guard let self else { return }
                                self.updateChatPresentationInterfaceState(interactive: false) { state in
                                    return state.updatedTranslationState(
                                        ChatPresentationTranslationState(isEnabled: true, fromLang: "de", toLang: "en")
                                    )
                                }
                            }
                        }
                        // Streaming catch-up: fires on EVERY chat open (deduped by catchUpInProgress set)
                        // Also detects bots (adds to botChatIds) and returns early
                        AIBackgroundTranslationObserver.translateMessages(peerId: chatPeerId, context: self.context)

                        // Async bot detection fallback: if catch-up discovers this is a bot,
                        // disable translation state after the fact
                        let _ = (self.context.account.postbox.transaction { transaction -> Bool in
                            if let peer = transaction.getPeer(chatPeerId) as? TelegramUser {
                                return peer.botInfo != nil
                            }
                            return false
                        } |> deliverOnMainQueue).start(next: { [weak self] isBot in
                            guard let self = self, isBot else { return }
                            AIBackgroundTranslationObserver.botChatIds.insert(aiPeerId64)
                            self.updateChatPresentationInterfaceState(interactive: false) { state in
                                return state.updatedTranslationState(nil)
                            }
                        })
                    }
                }
            }"""

    content = content.replace(target, override_code, 1)

    with open(filepath, "w") as f:
        f.write(content)

    print(f"Patched {filepath}: translation rendering + streaming catch-up")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path_to_ChatControllerLoadDisplayNode.swift>")
        sys.exit(1)

    patch_incoming_translation(sys.argv[1])
