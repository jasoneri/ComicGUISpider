use pep440_rs::Version;
use std::str::FromStr;

pub fn normalize_version(version: &str) -> (String, bool) {
    let cleaned = version.trim().trim_start_matches(['v', 'V']);
    match Version::from_str(cleaned) {
        Ok(ver) => (ver.to_string(), ver.is_pre()),
        Err(_) => (cleaned.to_string(), false),
    }
}

pub fn build_install_args(version: &str, index_url: &str, script: bool) -> Vec<String> {
    let (normalized, is_prerelease) = normalize_version(version);
    let package_name = if script {
        "ComicGUISpider[script]"
    } else {
        "ComicGUISpider"
    };
    let mut cmd = vec![
        "tool".into(),
        "install".into(),
        format!("{package_name}=={normalized}"),
    ];

    if !index_url.is_empty() {
        if index_url.starts_with("file://") {
            cmd.extend(["--extra-index-url".into(), index_url.to_string()]);
        } else {
            cmd.extend(["--index-url".into(), index_url.to_string()]);
        }
    }

    if is_prerelease {
        cmd.extend(["--prerelease".into(), "if-necessary-or-explicit".into()]);
    }
    cmd.push("--force".into());
    cmd
}
