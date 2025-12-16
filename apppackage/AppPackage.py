class AppPackageInfo:
    def __init__(self, name, package_name, app_version, ad_id_prefix: str | None = None):
        self.name = name
        self.package_name = package_name
        self.app_version = app_version
        self.id_prefix = self.package_name + ":id/"
        self.ad_id_prefix = ad_id_prefix


AppInfoKuaiShou = AppPackageInfo("kuaishou", "com.kuaishou.nebula", "1.0.0",
                                 ad_id_prefix="com.kuaishou.nebula.commercial_neo:id/")

AppInfoDouYin = AppPackageInfo("douyin", "com.ss.android.ugc.aweme.lite", "1.0.0",
                               ad_id_prefix="com.ss.android.ugc.aweme.lite:id/")
