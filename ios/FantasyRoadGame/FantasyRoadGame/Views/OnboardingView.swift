import SwiftUI

struct OnboardingView: View {
    @EnvironmentObject var store: GameStore

    @State private var playerOne: String = ""
    @State private var playerTwo: String = ""
    @State private var coupleMode: Bool = false
    @State private var agreed: Bool = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {

                    VStack(alignment: .leading, spacing: 8) {
                        Text("🚗✨")
                            .font(.system(size: 56))
                        Text("Дорога фантазий")
                            .font(.largeTitle.bold())
                        Text("Игра-разговор для двоих в дороге или дома. Карточки помогают легче говорить о желаниях и укреплять близость.")
                            .font(.body)
                            .foregroundStyle(.secondary)
                    }

                    VStack(alignment: .leading, spacing: 12) {
                        Label("Игра только для взрослых, по обоюдному желанию.", systemImage: "checkmark.seal")
                        Label("Любую карточку можно пропустить без объяснений.", systemImage: "forward.circle")
                        Label("Если вы за рулём — картами управляет пассажир.", systemImage: "car.fill")
                    }
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                    Divider()

                    VStack(alignment: .leading, spacing: 12) {
                        Text("Как вас называть?")
                            .font(.headline)

                        TextField("Игрок 1", text: $playerOne)
                            .textFieldStyle(.roundedBorder)

                        TextField("Игрок 2", text: $playerTwo)
                            .textFieldStyle(.roundedBorder)

                        Toggle("Показывать, чей сейчас ход", isOn: $coupleMode)
                    }

                    Toggle(isOn: $agreed) {
                        Text("Нам обоим есть 18 лет, мы играем добровольно и можем остановиться в любой момент.")
                            .font(.subheadline)
                    }

                    Button {
                        store.completeOnboarding(playerOne: playerOne, playerTwo: playerTwo, coupleMode: coupleMode)
                    } label: {
                        Text("Начать игру")
                            .font(.headline)
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .disabled(!agreed)
                }
                .padding(24)
            }
            .background(LevelTheme.gradient(for: 2).opacity(0.15).ignoresSafeArea())
        }
    }
}
