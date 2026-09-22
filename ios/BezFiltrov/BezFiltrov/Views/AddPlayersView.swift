import SwiftUI

struct AddPlayersView: View {
    @EnvironmentObject var store: SessionStore
    @State private var newName: String = ""
    @FocusState private var fieldFocused: Bool

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Text("Кто в игре?")
                    .font(.largeTitle.bold())
                    .foregroundStyle(Theme.textPrimary)

                Text("Имена или псевдонимы — как удобно. Это остаётся только на этом устройстве.")
                    .font(.subheadline)
                    .foregroundStyle(Theme.textPrimary.opacity(0.7))

                HStack {
                    TextField("Имя игрока", text: $newName)
                        .textFieldStyle(.roundedBorder)
                        .focused($fieldFocused)
                        .onSubmit(addPlayer)

                    Button("Добавить", action: addPlayer)
                        .buttonStyle(.bordered)
                        .tint(Theme.accentSecondary)
                        .disabled(newName.trimmingCharacters(in: .whitespaces).isEmpty)
                }

                if !store.players.isEmpty {
                    VStack(spacing: 10) {
                        ForEach(store.players) { player in
                            HStack {
                                Circle()
                                    .fill(Color(hex: player.avatarColorHex))
                                    .frame(width: 32, height: 32)
                                    .overlay(
                                        Text(String(player.displayName.prefix(1)).uppercased())
                                            .font(.subheadline.bold())
                                            .foregroundStyle(.white)
                                    )
                                Text(player.displayName)
                                    .foregroundStyle(Theme.textPrimary)
                                Spacer()
                                Button {
                                    store.removePlayer(player)
                                } label: {
                                    Image(systemName: "trash")
                                        .foregroundStyle(Theme.signalStop)
                                }
                                .buttonStyle(.plain)
                            }
                            .padding(12)
                            .background(Theme.backgroundCard)
                            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                        }
                    }
                }

                Button {
                    store.finishAddingPlayers()
                } label: {
                    Text("Дальше: согласие и границы")
                        .font(.headline)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 6)
                }
                .buttonStyle(.borderedProminent)
                .tint(Theme.accentPrimary)
                .controlSize(.large)
                .disabled(store.players.count < 2)

                if store.players.count < 2 {
                    Text("Нужно минимум два игрока.")
                        .font(.caption)
                        .foregroundStyle(Theme.textPrimary.opacity(0.5))
                }
            }
            .padding(28)
            .frame(maxWidth: 640)
            .frame(maxWidth: .infinity)
        }
    }

    private func addPlayer() {
        store.addPlayer(name: newName)
        newName = ""
        fieldFocused = true
    }
}
