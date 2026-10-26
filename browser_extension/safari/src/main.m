//
//  main.m
//  取货门店助手 · Safari 扩展的容器 App
//
//  Safari Web Extension 必须装在一个 macOS App 里发行。这个 App 本身只做两件事：
//    1) 承载 PlugIns/…appex，让 Safari 能发现这个扩展
//    2) 显示启用步骤，并提供一个按钮直接跳到 Safari 的扩展设置
//  它不联网、不读取任何用户数据、不访问 Apple 任何接口。
//

#import <Cocoa/Cocoa.h>
#import <SafariServices/SafariServices.h>

static NSString *const kExtensionIdentifier = @"com.duomonitor.storeselector.Extension";

static NSString *const kSteps =
    @"取货门店助手 · Safari 版\n"
    @"\n"
    @"启用步骤（只需做一次，按顺序点）：\n"
    @"\n"
    @"1. Safari 菜单栏 → Safari → 设置 → 高级 →\n"
    @"   勾选“显示网页开发者功能”（或“在菜单栏中显示开发菜单”）\n"
    @"\n"
    @"2. Safari 菜单栏 → 开发 → 勾选“允许未签名的扩展”\n"
    @"   （这个开关每次重新启动 Safari 都要重新勾一次）\n"
    @"\n"
    @"3. Safari 菜单栏 → Safari → 设置 → 扩展 →\n"
    @"   勾选“iPhone Duo Monitor 取货门店助手”\n"
    @"\n"
    @"4. 同一页面点“编辑网站”，把 www.apple.com.cn 设为“允许”\n"
    @"\n"
    @"扩展只在 https://www.apple.com.cn/shop/* 上运行。它会自动点开“查看供货情况”，\n"
    @"等 Apple 自己加载出取货门店列表后选中优先级最高且仍可取货的门店，然后停住。\n"
    @"它绝不会点“继续”、不加入购物袋、不结账、不付款。";

@interface AppDelegate : NSObject <NSApplicationDelegate>
@property (strong) NSWindow *window;
@end

@implementation AppDelegate

- (void)applicationDidFinishLaunching:(NSNotification *)note {
    NSRect frame = NSMakeRect(0, 0, 560, 460);
    self.window = [[NSWindow alloc]
        initWithContentRect:frame
                  styleMask:(NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable)
                    backing:NSBackingStoreBuffered
                      defer:NO];
    [self.window setTitle:@"取货门店助手"];
    [self.window center];

    NSView *content = [self.window contentView];

    NSTextField *label = [[NSTextField alloc] initWithFrame:NSMakeRect(24, 76, 512, 360)];
    [label setStringValue:kSteps];
    [label setBezeled:NO];
    [label setDrawsBackground:NO];
    [label setEditable:NO];
    [label setSelectable:YES];
    [label setFont:[NSFont systemFontOfSize:12]];
    [[label cell] setWraps:YES];
    [content addSubview:label];

    NSButton *button = [[NSButton alloc] initWithFrame:NSMakeRect(24, 24, 260, 32)];
    [button setTitle:@"打开 Safari 扩展设置"];
    [button setBezelStyle:NSBezelStyleRounded];
    [button setTarget:self];
    [button setAction:@selector(openExtensionPreferences:)];
    [content addSubview:button];

    NSTextField *status = [[NSTextField alloc] initWithFrame:NSMakeRect(296, 30, 240, 20)];
    [status setStringValue:@""];
    [status setBezeled:NO];
    [status setDrawsBackground:NO];
    [status setEditable:NO];
    [status setFont:[NSFont systemFontOfSize:11]];
    [status setTag:99];
    [content addSubview:status];

    [self.window makeKeyAndOrderFront:nil];
    [NSApp activateIgnoringOtherApps:YES];
}

- (void)openExtensionPreferences:(id)sender {
    [SFSafariApplication showPreferencesForExtensionWithIdentifier:kExtensionIdentifier
                                                 completionHandler:^(NSError *error) {
        dispatch_async(dispatch_get_main_queue(), ^{
            NSTextField *status = [[self.window contentView] viewWithTag:99];
            if (error) {
                [status setStringValue:@"打不开，请按左边步骤手动操作"];
            } else {
                [status setStringValue:@"已打开 Safari 扩展设置"];
            }
        });
    }];
}

- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender {
    return YES;
}

@end

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        NSApplication *app = [NSApplication sharedApplication];
        AppDelegate *delegate = [[AppDelegate alloc] init];
        [app setDelegate:delegate];
        [app setActivationPolicy:NSApplicationActivationPolicyRegular];
        [app run];
    }
    return 0;
}
