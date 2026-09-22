import SwiftUI

struct GameView: View {

    enum Mode: String, CaseIterable, Identifiable {
        case cards = "Карточки"
        case scenario = "Сценарий"
        var id: String { rawValue }
    }

    @EnvironmentObject var store: GameStore
    @State private var mode: Mode = .cards

    @State private var dragOffset: CGSize = .zero
    @State private var flipAngle: Double = 0
    @State private var cardOpacity: Double = 1

    @State private var currentScenario: GeneratedScenario?

    var body: some View {
        NavigationStack {
            GeometryReader { geometry in
                if geometry.size.width > 780 {
                    HStack(alignment: .top, spacing: 28) {
                        LevelPickerView(style: .list)
                            .frame(width: 280)

                        ScrollView {
                            gameContent
                        }
                    }
                    .padding(24)
                } else {
                    ScrollView {
                        VStack(spacing: 20) {
                            LevelPickerView(style: .chips)
                            gameContent
                        }
                        .padding(18)
                    }
                }
            }
            .navigationTitle("Дорога фантазий")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private var gameContent: some View {
        VStack(spacing: 18) {

            Picker("Режим", selection: $mode) {
                ForEach(Mode.allCases) { pickerMode in
                    Text(pickerMode.rawValue).tag(pickerMode)
                }
            }
            .pickerStyle(.segmented)

            ProgressHeaderView()

            if store.settings.coupleModeEnabled {
                TurnBadgeView()
            }

            switch mode {
            case .cards:
                cardsContent
            case .scenario:
                scenarioContent
            }
        }
        .onChange(of: store.selectedLevelID) { _, _ in
            currentScenario = nil
        }
    }

    private var cardsContent: some View {
        VStack(spacing: 18) {
            if let card = store.currentCard {
                CardView(card: card)
                    .offset(dragOffset)
                    .rotationEffect(.degrees(Double(dragOffset.width / 18)))
                    .rotation3DEffect(.degrees(flipAngle), axis: (x: 0, y: 1, z: 0))
                    .opacity(cardOpacity)
                    .gesture(dragGesture)
                    .animation(.interactiveSpring(), value: dragOffset)
            } else {
                emptyDeckView
            }

            actionButtons

            Text("Любую карточку можно пропустить без объяснений. Свайп влево — пропустить, вправо — в копилку.")
                .font(.footnote)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
    }

    private var scenarioContent: some View {
        VStack(spacing: 18) {
            if (1...5).contains(store.selectedLevelID) {
                ScenarioCardView(scenario: currentScenario)

                HStack(spacing: 16) {
                    Button {
                        generateScenario()
                    } label: {
                        Label(currentScenario == nil ? "Сгенерировать" : "Ещё раз", systemImage: "shuffle")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)

                    Button {
                        saveScenario()
                    } label: {
                        Label("Сохранить", systemImage: "heart.fill")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.large)
                    .tint(.pink)
                    .disabled(currentScenario == nil)
                }

                Text("Случайное сочетание «где — когда — с кем — куда» для текущего уровня. Можно крутить сколько угодно раз.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            } else {
                unsupportedScenarioLevelView
            }
        }
        .onAppear {
            if currentScenario == nil {
                generateScenario()
            }
        }
    }

    private var unsupportedScenarioLevelView: some View {
        VStack(spacing: 14) {
            Text("🎲")
                .font(.system(size: 44))
            Text("Конструктор сценариев работает для уровней 1–5")
                .font(.headline)
            Text("Выберите один из основных уровней, чтобы собрать случайный сценарий вечера.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(40)
        .frame(maxWidth: .infinity)
        .background(Color.secondary.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
    }

    private var emptyDeckView: some View {
        VStack(spacing: 14) {
            Text("✏️")
                .font(.system(size: 44))
            Text("В этой колоде пока нет карточек")
                .font(.headline)
            Text("Добавьте свои вопросы во вкладке «Настройки», и они появятся здесь.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(40)
        .frame(maxWidth: .infinity)
        .background(Color.secondary.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
    }

    private var actionButtons: some View {
        HStack(spacing: 16) {
            Button {
                skip()
            } label: {
                Label("Пропустить", systemImage: "forward.fill")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .controlSize(.large)
            .disabled(store.currentCard == nil)

            Button {
                saveAndAdvance()
            } label: {
                Label("В копилку", systemImage: "heart.fill")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .controlSize(.large)
            .tint(.pink)
            .disabled(store.currentCard == nil)

            Button {
                advance()
            } label: {
                Label("Дальше", systemImage: "arrow.right.circle.fill")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(store.currentCard == nil)
        }
    }

    private var dragGesture: some Gesture {
        DragGesture()
            .onChanged { value in
                dragOffset = value.translation
            }
            .onEnded { value in
                if value.translation.width < -110 {
                    skip()
                } else if value.translation.width > 110 {
                    saveAndAdvance()
                } else {
                    dragOffset = .zero
                }
            }
    }

    private func skip() {
        dragOffset = .zero
        advance()
    }

    private func saveAndAdvance() {
        if let card = store.currentCard, !store.isFavorite(card) {
            store.toggleFavorite(card)
        }
        dragOffset = .zero
        advance()
    }

    private func advance() {
        withAnimation(.easeIn(duration: 0.16)) {
            flipAngle = 90
            cardOpacity = 0
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.16) {
            store.drawNextCard()
            flipAngle = -90
            withAnimation(.easeOut(duration: 0.22)) {
                flipAngle = 0
                cardOpacity = 1
            }
        }
    }

    private func generateScenario() {
        currentScenario = store.generateScenario()
    }

    private func saveScenario() {
        guard let scenario = currentScenario else { return }
        store.saveScenario(scenario)
    }
}
