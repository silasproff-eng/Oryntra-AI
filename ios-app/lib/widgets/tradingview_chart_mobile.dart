import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

class TradingViewChart extends StatefulWidget {
  const TradingViewChart({super.key, required this.symbol, this.height = 350});

  final String symbol;
  final double height;

  @override
  State<TradingViewChart> createState() => _TradingViewChartState();
}

class _TradingViewChartState extends State<TradingViewChart> {
  late final WebViewController _controller;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(const Color(0xFF07111F))
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageFinished: (_) {
            if (mounted) setState(() => _loading = false);
          },
          onWebResourceError: (error) {
            if (error.isForMainFrame == true && mounted) {
              setState(() {
                _loading = false;
                _error = 'TradingView chart is temporarily unavailable.';
              });
            }
          },
          onNavigationRequest: (request) {
            final uri = Uri.tryParse(request.url);
            if (uri == null) return NavigationDecision.prevent;
            if (uri.scheme == 'about' ||
                uri.host.endsWith('tradingview.com') ||
                uri.host.endsWith('tradingview-widget.com')) {
              return NavigationDecision.navigate;
            }
            return NavigationDecision.prevent;
          },
        ),
      )
      ..loadHtmlString(
        _html(widget.symbol),
        baseUrl: 'https://www.tradingview.com',
      );
  }

  @override
  void didUpdateWidget(covariant TradingViewChart oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.symbol != widget.symbol) {
      setState(() {
        _loading = true;
        _error = null;
      });
      _controller.loadHtmlString(
        _html(widget.symbol),
        baseUrl: 'https://www.tradingview.com',
      );
    }
  }

  String _html(String rawSymbol) {
    final symbol = rawSymbol.trim().isEmpty ? 'NASDAQ:AAPL' : rawSymbol.trim();
    final config = jsonEncode({
      'autosize': true,
      'symbol': symbol,
      'interval': 'D',
      'timezone': 'exchange',
      'theme': 'dark',
      'style': '1',
      'locale': 'en',
      'backgroundColor': '#07111F',
      'gridColor': 'rgba(56, 207, 243, 0.08)',
      'hide_top_toolbar': true,
      'hide_side_toolbar': true,
      'hide_legend': true,
      'hide_volume': true,
      'withdateranges': false,
      'allow_symbol_change': false,
      'save_image': false,
      'details': false,
      'hotlist': false,
      'calendar': false,
      'support_host': 'https://www.tradingview.com',
    });
    return '''<!doctype html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<style>
html,body{width:100%;height:100%;margin:0;overflow:hidden;background:#07111f;color:#9fb4c7;font-family:-apple-system,BlinkMacSystemFont,sans-serif}
.tradingview-widget-container{width:100%;height:100%;background:#07111f}
.tradingview-widget-container__widget{width:100%;height:calc(100% - 28px)}
.tradingview-widget-copyright{height:28px;display:flex;align-items:center;justify-content:center;font-size:10px;background:#07111f}
.tradingview-widget-copyright a{color:#38cff3;text-decoration:none;font-weight:700}
</style></head><body>
<div class="tradingview-widget-container">
<div class="tradingview-widget-container__widget"></div>
<div class="tradingview-widget-copyright"><a href="https://www.tradingview.com/" rel="noopener nofollow" target="_blank">Chart by TradingView</a></div>
<script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js" async>$config</script>
</div></body></html>''';
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: widget.height,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(18),
        child: Stack(
          fit: StackFit.expand,
          children: [
            ColoredBox(
              color: const Color(0xFF07111F),
              child: _error == null
                  ? WebViewWidget(controller: _controller)
                  : Center(
                      child: Padding(
                        padding: const EdgeInsets.all(18),
                        child: Text(
                          _error!,
                          textAlign: TextAlign.center,
                          style: const TextStyle(color: Colors.white70),
                        ),
                      ),
                    ),
            ),
            if (_loading)
              const ColoredBox(
                color: Color(0xCC07111F),
                child: Center(child: CircularProgressIndicator()),
              ),
          ],
        ),
      ),
    );
  }
}
