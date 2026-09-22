import SwiftUI

struct LevelPickerView: View {
    enum Style {
        case list
        case chips
    }

    @EnvironmentObject var store: GameStore
    let style: Style

    var body: some View {
        switch style {
        case .list:
            listBody
        case .chips:
            chipsBody
        }
    }

    private var listBody: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("Уровень")
                    .font(.title2.bold())

                Spacer()

                Button {
                    store.selectRandomLevel()
                } label: {
                    Label("Наугад", systemImage: "shuffle")
                        .font(.caption.bold())
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }

            Text("Начните легко и повышайте уровень, только когда обоим комфортно.")
                .font(.subheadline)
                .foregroundStyle(.secondary)

            ForEach(store.levels) { level in
                levelRow(level)
            }

            Divider()
                .padding(.vertical, 6)

            Label(
                "Пассажир управляет игрой. Водитель только отвечает.",
                systemImage: "car.fill"
            )
            .font(.footnote)
            .foregroundStyle(.secondary)
        }
    }

    private var chipsBody: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                Button {
                    store.selectRandomLevel()
                } label: {
                    Image(systemName: "shuffle")
                        .font(.subheadline.bold())
                        .padding(10)
                        .background(Color.secondary.opacity(0.1))
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Случайный уровень")

                ForEach(store.levels) { level in
                    Button {
                        store.selectLevel(level.id)
                    } label: {
                        HStack(spacing: 6) {
                            Text(level.emoji)
                            Text(level.title)
                                .font(.subheadline.bold())
                        }
                        .padding(.horizontal, 14)
                        .padding(.vertical, 10)
                        .background(
                            store.selectedLevelID == level.id
                                ? AnyShapeStyle(LevelTheme.gradient(for: level.id))
                                : AnyShapeStyle(Color.secondary.opacity(0.1))
                        )
                        .foregroundStyle(store.selectedLevelID == level.id ? .white : .primary)
                        .clipShape(Capsule())
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 2)
        }
    }

    private func levelRow(_ level: GameLevel) -> some View {
        Button {
            store.selectLevel(level.id)
        } label: {
            HStack {
                Text(level.emoji)
                    .font(.title2)

                VStack(alignment: .leading) {
                    Text(level.title)
                        .font(.headline)
                    Text(level.subtitle)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                Spacer()

                if let played = store.stats.perLevelPlayed[level.id], played > 0 {
                    Text("\(played)")
                        .font(.caption.bold())
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color.secondary.opacity(0.12))
                        .clipShape(Capsule())
                }

                if store.selectedLevelID == level.id {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.title3)
                        .foregroundStyle(.tint)
                }
            }
            .padding(14)
            .background(
                store.selectedLevelID == level.id
                    ? Color.accentColor.opacity(0.15)
                    : Color.secondary.opacity(0.08)
            )
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        }
        .buttonStyle(.plain)
    }
}
