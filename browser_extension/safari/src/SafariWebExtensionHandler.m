//
//  SafariWebExtensionHandler.m
//  取货门店助手 · Safari Web Extension 的原生处理器
//
//  Safari 要求每个 Web Extension 的 appex 声明一个 NSExtensionPrincipalClass。
//  本扩展不使用 native messaging，所以这个类只把请求原样结束掉，什么都不做：
//  不读 Cookie、不读 Apple ID、不发网络请求、不碰任何 Apple 接口。
//  真正的门店选择逻辑全部在 Resources/store_selector_core.js 里，和 Chrome 版是同一份文件。
//

#import <Foundation/Foundation.h>

@interface SafariWebExtensionHandler : NSObject <NSExtensionRequestHandling>
@end

@implementation SafariWebExtensionHandler

- (void)beginRequestWithExtensionContext:(NSExtensionContext *)context {
    // 不处理任何消息，立即完成。没有任何数据流出扩展。
    [context completeRequestReturningItems:@[] completionHandler:nil];
}

@end
