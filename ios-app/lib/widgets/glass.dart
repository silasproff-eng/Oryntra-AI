import 'dart:ui';
import 'package:flutter/material.dart';

class OryntraPalette {
  static const navy = Color(0xFF071A32);
  static const deepNavy = Color(0xFF030B18);
  static const panel = Color(0xFF0C203A);
  static const panelRaised = Color(0xFF112B49);
  static const ink = Color(0xFFF3F7FC);
  static const muted = Color(0xFF9CB0C7);
  static const blue = Color(0xFF3B82C4);
  static const blueBright = Color(0xFF7CC2FF);
  static const green = Color(0xFF8CC4AD);
  static const rule = Color(0xFF274663);
  static const danger = Color(0xFFF18A9B);
}

class OryntraColors {
  const OryntraColors._({
    required this.navy,
    required this.deepNavy,
    required this.panel,
    required this.panelRaised,
    required this.ink,
    required this.muted,
    required this.blue,
    required this.blueBright,
    required this.green,
    required this.rule,
    required this.danger,
  });

  final Color navy;
  final Color deepNavy;
  final Color panel;
  final Color panelRaised;
  final Color ink;
  final Color muted;
  final Color blue;
  final Color blueBright;
  final Color green;
  final Color rule;
  final Color danger;

  static OryntraColors of(BuildContext context) {
    if (Theme.of(context).brightness == Brightness.dark) {
      return const OryntraColors._(
        navy: OryntraPalette.navy,
        deepNavy: OryntraPalette.deepNavy,
        panel: OryntraPalette.panel,
        panelRaised: OryntraPalette.panelRaised,
        ink: OryntraPalette.ink,
        muted: OryntraPalette.muted,
        blue: OryntraPalette.blue,
        blueBright: OryntraPalette.blueBright,
        green: OryntraPalette.green,
        rule: OryntraPalette.rule,
        danger: OryntraPalette.danger,
      );
    }
    return const OryntraColors._(
      navy: Color(0xFFEAF1F8),
      deepNavy: Color(0xFFF7F9FC),
      panel: Color(0xFFFFFFFF),
      panelRaised: Color(0xFFF0F5FA),
      ink: Color(0xFF13263C),
      muted: Color(0xFF5D7187),
      blue: Color(0xFF236EAA),
      blueBright: Color(0xFF17629E),
      green: Color(0xFF26735D),
      rule: Color(0xFFD5E0EA),
      danger: Color(0xFFB83B50),
    );
  }
}

class LiquidGlass extends StatelessWidget {
  const LiquidGlass({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(16),
    this.radius = 20,
    this.opacity = .94,
  });

  final Widget child;
  final EdgeInsets padding;
  final double radius;
  final double opacity;

  @override
  Widget build(BuildContext context) {
    final colors = OryntraColors.of(context);
    final border = BorderRadius.circular(radius);
    return ClipRRect(
      borderRadius: border,
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 14, sigmaY: 14),
        child: DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: border,
            color: colors.panel.withValues(alpha: opacity),
            border: Border.all(color: colors.rule),
            boxShadow: const [
              BoxShadow(
                color: Color(0x52000000),
                blurRadius: 22,
                offset: Offset(0, 10),
              ),
            ],
          ),
          child: Padding(padding: padding, child: child),
        ),
      ),
    );
  }
}

class GlassNavigationBar extends StatelessWidget {
  const GlassNavigationBar({
    super.key,
    required this.index,
    required this.onChanged,
  });

  final int index;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    final colors = OryntraColors.of(context);
    const items = [
      (Icons.search_rounded, 'Scanner'),
      (Icons.bookmark_border_rounded, 'Watchlist'),
      (Icons.assignment_outlined, 'Paper'),
      (Icons.tune_rounded, 'Account'),
    ];
    return SafeArea(
      minimum: const EdgeInsets.fromLTRB(12, 0, 12, 12),
      child: LiquidGlass(
        radius: 24,
        padding: const EdgeInsets.all(5),
        opacity: .96,
        child: Row(
          children: List.generate(items.length, (itemIndex) {
            final selected = itemIndex == index;
            return Expanded(
              child: Semantics(
                selected: selected,
                button: true,
                label: items[itemIndex].$2,
                child: InkWell(
                  borderRadius: BorderRadius.circular(18),
                  onTap: () => onChanged(itemIndex),
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 240),
                    curve: Curves.easeOutCubic,
                    padding: const EdgeInsets.symmetric(vertical: 9),
                    decoration: BoxDecoration(
                      color: selected ? colors.panelRaised : Colors.transparent,
                      borderRadius: BorderRadius.circular(18),
                      border: selected
                          ? Border.all(color: colors.blue.withValues(alpha: .7))
                          : null,
                    ),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          items[itemIndex].$1,
                          size: 20,
                          color: selected ? colors.blueBright : colors.muted,
                        ),
                        const SizedBox(height: 4),
                        Text(
                          items[itemIndex].$2.toUpperCase(),
                          maxLines: 1,
                          style: TextStyle(
                            fontSize: 9,
                            height: 1,
                            letterSpacing: .55,
                            fontWeight: selected
                                ? FontWeight.w800
                                : FontWeight.w600,
                            color: selected ? colors.ink : colors.muted,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            );
          }),
        ),
      ),
    );
  }
}
