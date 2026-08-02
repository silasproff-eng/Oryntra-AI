import 'package:flutter/material.dart';
import 'package:google_mobile_ads/google_mobile_ads.dart';
import '../app_config.dart';

class AdaptiveBanner extends StatefulWidget {
  const AdaptiveBanner({super.key});

  @override
  State<AdaptiveBanner> createState() => _AdaptiveBannerState();
}

class _AdaptiveBannerState extends State<AdaptiveBanner> {
  BannerAd? _ad;
  AdSize? _size;
  int? _loadedWidth;

  Future<void> _load(int width) async {
    if (width <= 0 || width == _loadedWidth) return;
    _loadedWidth = width;
    final size = await AdSize.getLargeAnchoredAdaptiveBannerAdSize(width);
    if (size == null || !mounted) return;
    await _ad?.dispose();
    final ad = BannerAd(
      adUnitId: AppConfig.bannerAdUnitId,
      size: size,
      request: const AdRequest(),
      listener: BannerAdListener(
        onAdLoaded: (loaded) {
          if (!mounted) {
            loaded.dispose();
            return;
          }
          setState(() {
            _ad = loaded as BannerAd;
            _size = size;
          });
        },
        onAdFailedToLoad: (failed, error) {
          failed.dispose();
          if (mounted) setState(() => _ad = null);
        },
      ),
    );
    await ad.load();
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.maxWidth.floor();
        WidgetsBinding.instance.addPostFrameCallback((_) => _load(width));
        if (_ad == null || _size == null) return const SizedBox.shrink();
        return Semantics(
          label: 'Advertisement',
          child: SizedBox(
            width: _size!.width.toDouble(),
            height: _size!.height.toDouble(),
            child: AdWidget(ad: _ad!),
          ),
        );
      },
    );
  }

  @override
  void dispose() {
    _ad?.dispose();
    super.dispose();
  }
}
