class AppPackageInfo:
    def __init__(self, name, package_name, app_version, enable_balance: bool, ad_id_prefix: str | None = None):
        self.name = name
        self.package_name = package_name
        self.app_version = app_version
        self.enable_balance = enable_balance
        self.id_prefix = self.package_name + ":id/"
        self.ad_id_prefix = ad_id_prefix


AppInfoKuaiShou = AppPackageInfo("kuaishou", "com.kuaishou.nebula", "1.0.0", True,
                                 ad_id_prefix="com.kuaishou.nebula.commercial_neo:id/")

AppInfoDouYin = AppPackageInfo("douyin", "com.ss.android.ugc.aweme.lite", "1.0.0", False,
                               ad_id_prefix="com.ss.android.ugc.aweme.lite:id/")
