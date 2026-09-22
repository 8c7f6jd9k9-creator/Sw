import SwiftUI

/// Final screen after any session end, hot or not. Same "pass the device"
/// pattern as consent: private per player, nobody sees another's answers.
struct AftercareFlowView: View {
    @EnvironmentObject var store: SessionStore

    @State private var currentIndex = 0
    @State private var isShowingForm = false
    @State private var feeling = ""
    @State private var whatWorked = ""
    @State private var whatToAvoid = ""

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
                    .onAppear { store.finishAftercare() }
            }
        }
    }

    private func handoffView(for player: Player) -> some View {
        VStack(spacing: 24) {
            Image(systemName: "heart.circle.fill")
                .font(.system(size: 56))
                .foregroundStyle(Theme.signalSafe)

            Text("Aftercare")
                .font(.title.bold())
                .foregroundStyle(Theme.textPrimary)

            Text("Передайте устройство \(player.displayName). Это приватно — остальные не увидят ответ.")
                .font(.subheadline)
                .foregroundStyle(Theme.textPrimary.opacity(0.7))
                .multilineTextAlignment(.center)

            Button {
                resetForm()
                isShowingForm = true
            } label: {
                Text("Я \(player.displayName)")
                    .font(.headline)
                    .padding(.horizontal, 20)
                    .padding(.vertical, 10)
            }
            .buttonStyle(.borderedProminent)
            .tint(Theme.signalSafe)
        }
        .padding(40)
        .frame(maxWidth: 520)
    }

    private func formView(for player: Player) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text("Как ты себя чувствуешь?")
                    .font(.title2.bold())
                    .foregroundStyle(Theme.textPrimary)

                promptField(title: "Как ты себя чувствуешь?", text: $feeling)
                promptField(title: "Что понравилось?", text: $whatWorked)
                promptField(title: "Что лучше не повторять?", text: $whatToAvoid)

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
            }
            .padding(28)
            .frame(maxWidth: 640)
            .frame(maxWidth: .infinity)
        }
    }

    private func promptField(title: String, text: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.subheadline).foregroundStyle(Theme.textPrimary.opacity(0.8))
            TextField("Необязательно", text: text, axis: .vertical)
                .lineLimit(2...4)
                .textFieldStyle(.roundedBorder)
        }
    }

    private var isLastPlayer: Bool {
        currentIndex == store.players.count - 1
    }

    private func resetForm() {
        feeling = ""
        whatWorked = ""
        whatToAvoid = ""
    }

    private func submit(for player: Player) {
        store.recordAftercare(
            playerID: player.id,
            feeling: feeling,
            whatWorked: whatWorked,
            whatToAvoid: whatToAvoid
        )
        isShowingForm = false
        currentIndex += 1
    }
}
