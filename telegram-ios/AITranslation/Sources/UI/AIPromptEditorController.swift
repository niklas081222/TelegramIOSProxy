import Foundation
import UIKit
import Display
import SwiftSignalKit
import TelegramPresentationData
import AccountContext
import UndoUI

public func aiPromptEditorController(context: AccountContext) -> ViewController {
    let controller = AIPromptEditorViewController(context: context)
    return controller
}

private final class AIPromptEditorViewController: ViewController {
    private let context: AccountContext
    private var textView: UITextView?
    private var loadingLabel: UILabel?
    private var disposable: Disposable?

    init(context: AccountContext) {
        self.context = context
        super.init(navigationBarPresentationData: NavigationBarPresentationData(
            presentationData: context.sharedContext.currentPresentationData.with { $0 }
        ))
        self.title = "System Prompt"
        self.navigationItem.rightBarButtonItem = UIBarButtonItem(
            title: "Save",
            style: .done,
            target: self,
            action: #selector(saveTapped)
        )
    }

    required init(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    deinit {
        disposable?.dispose()
    }

    override func viewDidLoad() {
        super.viewDidLoad()

        let presentationData = self.context.sharedContext.currentPresentationData.with { $0 }
        self.view.backgroundColor = presentationData.theme.list.blocksBackgroundColor

        let loading = UILabel()
        loading.text = "Loading prompt..."
        loading.textColor = presentationData.theme.list.itemSecondaryTextColor
        loading.font = UIFont.systemFont(ofSize: 15)
        loading.textAlignment = .center
        loading.translatesAutoresizingMaskIntoConstraints = false
        self.view.addSubview(loading)
        self.loadingLabel = loading

        NSLayoutConstraint.activate([
            loading.centerXAnchor.constraint(equalTo: self.view.centerXAnchor),
            loading.centerYAnchor.constraint(equalTo: self.view.centerYAnchor)
        ])

        let tv = UITextView()
        tv.font = UIFont.monospacedSystemFont(ofSize: 14, weight: .regular)
        tv.textColor = presentationData.theme.list.itemPrimaryTextColor
        tv.backgroundColor = presentationData.theme.list.itemBlocksBackgroundColor
        tv.layer.cornerRadius = 10
        tv.textContainerInset = UIEdgeInsets(top: 12, left: 8, bottom: 12, right: 8)
        tv.translatesAutoresizingMaskIntoConstraints = false
        tv.alpha = 0
        tv.autocorrectionType = .no
        tv.autocapitalizationType = .none
        tv.spellCheckingType = .no
        self.view.addSubview(tv)
        self.textView = tv

        NSLayoutConstraint.activate([
            tv.topAnchor.constraint(equalTo: self.view.safeAreaLayoutGuide.topAnchor, constant: 16),
            tv.leadingAnchor.constraint(equalTo: self.view.leadingAnchor, constant: 16),
            tv.trailingAnchor.constraint(equalTo: self.view.trailingAnchor, constant: -16),
            tv.bottomAnchor.constraint(equalTo: self.view.safeAreaLayoutGuide.bottomAnchor, constant: -16)
        ])

        self.disposable = (AITranslationService.shared.getPrompt()
        |> deliverOnMainQueue).startStrict(next: { [weak self] prompt in
            guard let self = self else { return }
            self.loadingLabel?.removeFromSuperview()
            self.textView?.text = prompt
            UIView.animate(withDuration: 0.2) {
                self.textView?.alpha = 1
            }
        })
    }

    @objc private func saveTapped() {
        guard let text = textView?.text else { return }

        self.navigationItem.rightBarButtonItem?.isEnabled = false

        self.disposable = (AITranslationService.shared.setPrompt(text)
        |> deliverOnMainQueue).startStrict(next: { [weak self] success in
            guard let self = self else { return }
            self.navigationItem.rightBarButtonItem?.isEnabled = true

            let presentationData = self.context.sharedContext.currentPresentationData.with { $0 }
            let message = success ? "Prompt saved" : "Failed to save prompt"
            let undoController = UndoOverlayController(
                presentationData: presentationData,
                content: .info(
                    title: nil,
                    text: message,
                    timeout: nil,
                    customUndoText: nil
                ),
                elevatedLayout: false,
                action: { _ in return false }
            )
            self.context.sharedContext.mainWindow?.present(undoController, on: .root)

            if success {
                self.navigationController?.popViewController(animated: true)
            }
        })
    }
}
