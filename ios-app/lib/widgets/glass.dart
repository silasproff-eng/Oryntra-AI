import 'dart:ui';
import 'package:flutter/material.dart';

class LiquidGlass extends StatelessWidget {
  const LiquidGlass({super.key, required this.child, this.padding = const EdgeInsets.all(16), this.radius = 22, this.opacity = .58});
  final Widget child;
  final EdgeInsets padding;
  final double radius;
  final double opacity;

  @override
  Widget build(BuildContext context) {
    final border = BorderRadius.circular(radius);
    return ClipRRect(
      borderRadius: border,
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
        child: DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: border,
            color: const Color(0xFF071A2D).withValues(alpha: opacity),
            border: Border.all(color: const Color(0xFF38CFF3).withValues(alpha: .18)),
            boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: .20), blurRadius: 24, offset: const Offset(0, 12))],
          ),
          child: Padding(padding: padding, child: child),
        ),
      ),
    );
  }
}

class GlassNavigationBar extends StatelessWidget {
  const GlassNavigationBar({super.key, required this.index, required this.onChanged});
  final int index;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    const items = [
      (Icons.search_rounded, 'Scanner'),
      (Icons.bookmark_rounded, 'Watchlist'),
      (Icons.show_chart_rounded, 'Paper'),
      (Icons.settings_rounded, 'Settings'),
    ];
    return SafeArea(
      minimum: const EdgeInsets.fromLTRB(12, 0, 12, 10),
      child: LiquidGlass(
        radius: 28,
        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 7),
        opacity: .78,
        child: Row(
          children: List.generate(items.length, (i) {
            final selected = i == index;
            return Expanded(
              child: InkWell(
                borderRadius: BorderRadius.circular(20),
                onTap: () => onChanged(i),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 280),
                  curve: Curves.easeOutCubic,
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(20),
                    gradient: selected ? const LinearGradient(colors: [Color(0x5538CFF3), Color(0x4420AAED), Color(0x557697F4)]) : null,
                    color: selected ? null : Colors.transparent,
                  ),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(items[i].$1, size: 22, color: selected ? const Color(0xFF38CFF3) : Colors.white70),
                      const SizedBox(height: 3),
                      Text(items[i].$2, maxLines: 1, style: TextStyle(fontSize: 10, fontWeight: selected ? FontWeight.w700 : FontWeight.w500)),
                    ],
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
