import SwiftUI

/// Reachable from Pause at any time — PRD §11.7: consent can be withdrawn
/// whenever, for whatever reason, no explanation needed. Granting works the
/// same way in the other direction.
struct ConsentReviewView: View {
    @EnvironmentObject var store: SessionStore
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                ForEach(store.players) { player in
                    Section(player.displayName) {
                        ForEach(ConsentTopic.allCases) { topic in
                            Toggle(isOn: bindingForConsent(player: player, topic: topic)) {
                                Text(topic.title)
                            }
                            .tint(Theme.accentSecondary)
                        }
                    }
                }
            }
            .navigationTitle("Согласие сейчас")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Готово") { dismiss() }
                }
            }
        }
    }

    private func bindingForConsent(player: Player, topic: ConsentTopic) -> Binding<Bool> {
        Binding(
            get: { store.consentRecords[player.id]?.grantedTopics.contains(topic) ?? false },
            set: { isOn in
                if isOn {
                    store.grantConsent(playerID: player.id, topic: topic)
                } else {
                    store.revokeConsent(playerID: player.id, topic: topic)
                }
            }
        )
    }
}
