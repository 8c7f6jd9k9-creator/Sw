import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var store: GameStore

    @State private var playerOne: String = ""
    @State private var playerTwo: String = ""
    @State private var newCardText: String = ""
    @State private var newCardCategory: String = ""
    @State private var showResetFavoritesAlert = false
    @State private var showResetProgressAlert = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Игроки") {
                    TextField("Игрок 1", text: $playerOne)
                        .onSubmit { commitNames() }
                    TextField("Игрок 2", text: $playerTwo)
                        .onSubmit { commitNames() }
                    Toggle("Показывать, чей ход", isOn: Binding(
                        get: { store.settings.coupleModeEnabled },
                        set: { newValue in
                            store.settings.coupleModeEnabled = newValue
                            store.persistSettings()
                        }
                    ))
                }

                Section("Ощущения") {
                    Toggle("Вибрация", isOn: Binding(
                        get: { store.settings.hapticsEnabled },
                        set: { newValue in
                            store.settings.hapticsEnabled = newValue
                            store.persistSettings()
                        }
                    ))

                    Picker("Тема оформления", selection: Binding(
                        get: { store.settings.appearance },
                        set: { newValue in
                            store.settings.appearance = newValue
                            store.persistSettings()
                        }
                    )) {
                        ForEach(AppAppearance.allCases) { appearance in
                            Text(appearance.title).tag(appearance)
                        }
                    }
                }

                Section("Свои карточки") {
                    TextField("Текст вопроса или задания", text: $newCardText, axis: .vertical)
                        .lineLimit(2...4)
                    TextField("Категория (необязательно)", text: $newCardCategory)
                    Button("Добавить карточку") {
                        store.addCustomCard(text: newCardText, category: newCardCategory)
                        newCardText = ""
                        newCardCategory = ""
                    }
                    .disabled(newCardText.trimmingCharacters(in: .whitespaces).isEmpty)

                    if !store.customCards.isEmpty {
                        ForEach(store.customCards) { card in
                            Text(card.text)
                                .font(.subheadline)
                                .swipeActions(edge: .trailing) {
                                    Button(role: .destructive) {
                                        store.removeCustomCard(card)
                                    } label: {
                                        Label("Удалить", systemImage: "trash")
                                    }
                                }
                        }
                    }
                }

                Section("Статистика") {
                    LabeledContent("Сыграно карточек", value: "\(store.stats.totalCardsPlayed)")
                    LabeledContent("В копилке", value: "\(store.favoriteIDs.count)")
                    LabeledContent("Сохранено сценариев", value: "\(store.savedScenarios.count)")
                    LabeledContent("Достижения", value: "\(unlockedAchievementsCount)/\(AchievementCatalog.all.count)")
                }

                Section("Достижения") {
                    ForEach(AchievementCatalog.all) { achievement in
                        let unlocked = achievement.isUnlocked(store)
                        HStack(spacing: 12) {
                            Image(systemName: unlocked ? achievement.icon : "lock.fill")
                                .font(.title3)
                                .foregroundStyle(unlocked ? Color.accentColor : .secondary)
                                .frame(width: 28)

                            VStack(alignment: .leading, spacing: 2) {
                                Text(achievement.title)
                                    .font(.subheadline.bold())
                                    .foregroundStyle(unlocked ? .primary : .secondary)
                                Text(achievement.subtitle)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }

                            Spacer()

                            if unlocked {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundStyle(.green)
                            }
                        }
                        .opacity(unlocked ? 1 : 0.55)
                    }
                }

                Section("Сброс") {
                    Button("Очистить копилку", role: .destructive) {
                        showResetFavoritesAlert = true
                    }
                    Button("Сбросить прогресс и статистику", role: .destructive) {
                        showResetProgressAlert = true
                    }
                }

                Section("О приложении") {
                    Text("«Дорога фантазий» — игра-разговор для двоих. Любую карточку можно пропустить. Игра предназначена только для взрослых по обоюдному согласию и не заменяет отдельный разговор о границах.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Настройки")
            .onAppear {
                playerOne = store.settings.playerOneName
                playerTwo = store.settings.playerTwoName
            }
            .alert("Очистить копилку?", isPresented: $showResetFavoritesAlert) {
                Button("Отмена", role: .cancel) {}
                Button("Очистить", role: .destructive) { store.resetFavorites() }
            } message: {
                Text("Все сохранённые карточки и сценарии будут удалены безвозвратно.")
            }
            .alert("Сбросить прогресс?", isPresented: $showResetProgressAlert) {
                Button("Отмена", role: .cancel) {}
                Button("Сбросить", role: .destructive) { store.resetProgress() }
            } message: {
                Text("Статистика сыгранных карточек будет обнулена.")
            }
        }
    }

    private func commitNames() {
        store.settings.playerOneName = playerOne.isEmpty ? "Игрок 1" : playerOne
        store.settings.playerTwoName = playerTwo.isEmpty ? "Игрок 2" : playerTwo
        store.persistSettings()
    }

    private var unlockedAchievementsCount: Int {
        AchievementCatalog.all.filter { $0.isUnlocked(store) }.count
    }
}
