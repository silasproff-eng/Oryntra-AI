import 'dart:async';
import 'package:google_mobile_ads/google_mobile_ads.dart';

class ConsentService {
  bool _startedAds = false;

  Future<bool> gatherConsentAndInitializeAds() async {
    final completer = Completer<bool>();
    final params = ConsentRequestParameters();

    ConsentInformation.instance.requestConsentInfoUpdate(
      params,
      () async {
        await ConsentForm.loadAndShowConsentFormIfRequired((error) async {
          final canRequest = await ConsentInformation.instance.canRequestAds();
          if (canRequest && !_startedAds) {
            _startedAds = true;
            await MobileAds.instance.initialize();
          }
          if (!completer.isCompleted) completer.complete(canRequest);
        });
      },
      (error) async {
        final canRequest = await ConsentInformation.instance.canRequestAds();
        if (canRequest && !_startedAds) {
          _startedAds = true;
          await MobileAds.instance.initialize();
        }
        if (!completer.isCompleted) completer.complete(canRequest);
      },
    );

    return completer.future.timeout(
      const Duration(seconds: 20),
      onTimeout: () => false,
    );
  }

  Future<bool> privacyOptionsRequired() async {
    final status = await ConsentInformation.instance
        .getPrivacyOptionsRequirementStatus();
    return status == PrivacyOptionsRequirementStatus.required;
  }

  Future<void> showPrivacyOptions() async {
    final completer = Completer<void>();
    ConsentForm.showPrivacyOptionsForm((error) {
      if (!completer.isCompleted) completer.complete();
    });
    return completer.future;
  }
}
