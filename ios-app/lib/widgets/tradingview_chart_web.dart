import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

class TradingViewChart extends StatelessWidget {
  const TradingViewChart({super.key, required this.symbol, this.height = 350});

  final String symbol;
  final double height;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: height,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: const Color(0xFF07111F),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: const Color(0x3338CFF3)),
        ),
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.candlestick_chart, size: 42, color: Color(0xFF38CFF3)),
                const SizedBox(height: 12),
                Text(symbol, style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 20)),
                const SizedBox(height: 8),
                const Text('The TradingView chart is available in the iOS app.', textAlign: TextAlign.center),
                const SizedBox(height: 16),
                OutlinedButton(
                  onPressed: () => launchUrl(
                    Uri.parse('https://www.tradingview.com/chart/?symbol=${Uri.encodeQueryComponent(symbol)}'),
                    mode: LaunchMode.externalApplication,
                  ),
                  child: const Text('Open TradingView'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
