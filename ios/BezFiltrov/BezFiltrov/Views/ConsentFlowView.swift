import SwiftUI

/// Screen 4. One player at a time, in "pass the device" style: a handoff
/// screen names who goes next, then a private form for age, the three
/// separate consents, and per-topic boundaries. Nothing here is visible to
/// the next player once they take over.
struct ConsentFlowView: View {
    @EnvironmentObject var store: SessionStore

    @State private var currentIndex = 0
    @State private var isShowingForm = false
    @State private var ageConfirmed = false
    @State private var grantedTopics: Set<ConsentTopic> = []
    @State private var boundaries: [Topic: BoundaryLevel] = [:]

    private var currentPlayer: Player? {
        guard currentIndex < store.players.count else { return nil }
        return store.players[currentIndex]
    }

    var body: some View {
        Group {
            if let player = currentPlayer {
                if isShowingForm {
                    formView(for: player)
                } else {
                    handoffView(for: player)
                }
            } else {
                ProgressView()
                    .onAppear { store.finishConsent() }
            }
        }
    }

    private func handoffView(for player: Player) -> some View {
        VStack(spacing: 24) {
            Image(systemName: "lock.shield.fill")
                .font(.system(size: 56))
                .foregroundStyle(Theme.accentSecondary)

            Text("Передайте устройство")
                .font(.title.bold())
                .foregroundStyle(Theme.textPrimary)

            Text("Дальше — приватная часть для \(player.displayName). Остальные не увидят эти ответы.")
                .font(.subheadline)
                .foregroundStyle(Theme.textPrimary.opacity(0.7))
                .multilineTextAlignment(.center)

            Button {
                resetFormState()
                isShowingForm = true
            } label: {
                Text("Я \(player.displayName), начать")
                    .font(.headline)
                    .padding(.horizontal, 20)
                    .padding(.vertical, 10)
            }
            .buttonStyle(.borderedProminent)
            .tint(Theme.accentPrimary)
        }
        .padding(40)
        .frame(maxWidth: 520)
    }

    private func formView(for player: Player) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Text("Согласие: \(player.displayName)")
                    .font(.title.bold())
                    .foregroundStyle(Theme.textPrimary)

                Toggle(isOn: $ageConfirmed) {
                    Text("Мне есть 18 лет, я участвую добровольно и могу остановиться в любой момент.")
                        .foregroundStyle(Theme.textPrimary)
                }
                .tint(Theme.accentPrimary)

                sectionCard(title: "Отдельные согласия") {
                    ForEach(ConsentTopic.allCases) { topic in
                        Toggle(isOn: bindingForConsent(topic)) {
                            Text(topic.title).foregroundStyle(Theme.textPrimary)
                        }
                        .tint(Theme.accentSecondary)
                    }
                    Text("Каждое можно включить, оставить выключенным или отозвать позже в любой момент — это не влияет на остальные.")
                        .font(.caption)
                        .foregroundStyle(Theme.textPrimary.opacity(0.6))
                }

                sectionCard(title: "Твои границы по темам") {
                    Text("«Точно нет» от любого игрока полностью убирает тему из колоды на всю сессию.")
                        .font(.caption)
                        .foregroundStyle(Theme.textPrimary.opacity(0.6))

                    ForEach(store.availableTopics) { topic in
                        BoundaryPicker(
                            title: topic.title,
                            level: bindingForBoundary(topic)
                        )
                    }
                }

                Button {
                    submit(for: player)
                } label: {
                    Text(isLastPlayer ? "Готово" : "Дальше: следующий игрок")
                        .font(.headline)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 6)
                }
                .buttonStyle(.borderedProminent)
                .tint(Theme.accentPrimary)
                .controlSize(.large)
                .disabled(!ageConfirmed)
            }
            .padding(28)
            .frame(maxWidth: 640)
            .frame(maxWidth: .infinity)
        }
    }

    private var isLastPlayer: Bool {
        currentIndex == store.players.count - 1
    }

    private func bindingForConsent(_ topic: ConsentTopic) -> Binding<Bool> {
        Binding(
            get: { grantedTopics.contains(topic) },
            set: { isOn in
                if isOn { grantedTopics.insert(topic) } else { grantedTopics.remove(topic) }
            }
        )
    }

    private func bindingForBoundary(_ topic: Topic) -> Binding<BoundaryLevel> {
        Binding(
            get: { boundaries[topic] ?? .discussLater },
            set: { boundaries[topic] = $0 }
        )
    }

    private func resetFormState() {
        ageConfirmed = false
        grantedTopics = []
        boundaries = [:]
    }

    private func submit(for player: Player) {
        store.recordConsent(
            playerID: player.id,
            ageConfirmed: ageConfirmed,
            grantedTopics: grantedTopics,
            boundaries: boundaries
        )
        isShowingForm = false
        currentIndex += 1
    }

    private func sectionCard<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(title)
                .font(.headline)
                .foregroundStyle(Theme.textPrimary)
            content()
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.backgroundCard)
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
    }
}
