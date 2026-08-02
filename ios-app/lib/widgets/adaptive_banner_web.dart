import 'package:flutter/material.dart';

class AdaptiveBanner extends StatelessWidget {
  const AdaptiveBanner({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(minHeight: 54),
      alignment: Alignment.center,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(14),
        color: Colors.white.withValues(alpha: .035),
        border: Border.all(color: Colors.white.withValues(alpha: .08)),
      ),
      child: const Text(
        'Advertisement area · hidden in browser preview',
        textAlign: TextAlign.center,
        style: TextStyle(fontSize: 11, color: Colors.white54),
      ),
    );
  }
}
